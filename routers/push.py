# routers/push.py
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database import get_db
from core.security import get_current_jugador
from schemas.push import PushTokenUpsert, PushSendToJugador, PushSendToMe
from models import PushToken
from core.firebase_admin import send_push_to_tokens

router = APIRouter(prefix="/push", tags=["Push"])


def _valid_tokens(rows):
    # filtra + dedupe (1 noti por token real)
    tokens = [t.fcm_token for t in rows if t.fcm_token and len(t.fcm_token) > 20]
    seen = set()
    out = []
    for tok in tokens:
        if tok in seen:
            continue
        seen.add(tok)
        out.append(tok)
    return out


@router.post("/token")
def save_push_token(
    payload: PushTokenUpsert,
    db: Session = Depends(get_db),
    jugador=Depends(get_current_jugador),
):
    token = (payload.fcm_token or "").strip()

    if not token or len(token) < 20:
        raise HTTPException(status_code=400, detail="FCM token inválido")

    existing = (
        db.query(PushToken)
        .filter(PushToken.jugador_id == jugador.id, PushToken.fcm_token == token)
        .first()
    )

    now = datetime.utcnow()

    if existing:
        # ✅ refrescar "último dispositivo activo"
        existing.created_at = now
        db.commit()
        return {"ok": True, "jugador_id": jugador.id, "saved": "refreshed"}

    db.add(PushToken(jugador_id=jugador.id, fcm_token=token, created_at=now))
    db.commit()

    return {"ok": True, "jugador_id": jugador.id, "saved": "inserted"}


@router.post("/send-to-me")
def send_to_me(
    payload: PushSendToMe,
    db: Session = Depends(get_db),
    jugador=Depends(get_current_jugador),
):
    rows = db.query(PushToken).filter(PushToken.jugador_id == jugador.id).all()
    if not rows:
        raise HTTPException(status_code=404, detail="Este jugador no tiene token registrado")

    token_list = _valid_tokens(rows)
    if not token_list:
        raise HTTPException(status_code=400, detail="Este jugador no tiene FCM tokens válidos guardados")

    result = send_push_to_tokens(
        token_list,
        title=payload.title,
        body=payload.body,
        data=payload.data or {"type": "test", "scope": "me"},
    )
    return {"jugador_id": jugador.id, **result}


@router.post("/send-to-jugador")
def send_to_jugador(
    payload: PushSendToJugador,
    db: Session = Depends(get_db),
    jugador=Depends(get_current_jugador),
):
    rows = db.query(PushToken).filter(PushToken.jugador_id == payload.jugador_id).all()
    if not rows:
        raise HTTPException(status_code=404, detail="Ese jugador no tiene token registrado")

    token_list = _valid_tokens(rows)
    if not token_list:
        raise HTTPException(status_code=400, detail="Ese jugador no tiene FCM tokens válidos guardados")

    result = send_push_to_tokens(
        token_list,
        title=payload.title,
        body=payload.body,
        data=payload.data or {"type": "test", "scope": "jugador", "from": str(jugador.id)},
    )
    return {"to_jugador_id": payload.jugador_id, **result}
