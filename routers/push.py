from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database import get_db
from core.security import get_current_jugador
from schemas.push import PushTokenUpsert, PushSendToJugador, PushSendToMe
from models import PushToken
from core.firebase_admin import send_push_to_tokens

router = APIRouter(prefix="/push", tags=["Push"])


def _is_probably_jwt(value: str) -> bool:
    v = (value or "").strip()
    return v.startswith("eyJ") and v.count(".") == 2


@router.post("/token")
def save_push_token(
    payload: PushTokenUpsert,
    db: Session = Depends(get_db),
    jugador=Depends(get_current_jugador),
):
    token = (payload.fcm_token or "").strip()

    # Validación base
    if not token or len(token) < 20:
        raise HTTPException(status_code=400, detail="FCM token inválido")

    # Guard rail: evitar que un JWT se guarde por error
    if _is_probably_jwt(token):
        raise HTTPException(status_code=400, detail="FCM token inválido (parece JWT)")

    # ✅ MULTI-DISPOSITIVO:
    # Guardamos el token si NO existe ya para este jugador.
    # (PC + Android + otros navegadores = múltiples filas)
    existing = (
        db.query(PushToken)
        .filter(PushToken.jugador_id == jugador.id, PushToken.fcm_token == token)
        .first()
    )

    if not existing:
        db.add(PushToken(jugador_id=jugador.id, fcm_token=token))

    db.commit()
    return {"ok": True, "jugador_id": jugador.id}


@router.post("/send-to-me")
def send_to_me(
    payload: PushSendToMe,
    db: Session = Depends(get_db),
    jugador=Depends(get_current_jugador),
):
    tokens = db.query(PushToken).filter(PushToken.jugador_id == jugador.id).all()
    if not tokens:
        raise HTTPException(status_code=404, detail="Este jugador no tiene token registrado")

    # Filtramos tokens inválidos (por si quedó basura vieja)
    token_list = []
    for t in tokens:
        fcm = (t.fcm_token or "").strip()
        if not fcm or len(fcm) < 20:
            continue
        if _is_probably_jwt(fcm):
            continue
        token_list.append(fcm)

    if not token_list:
        raise HTTPException(
            status_code=400,
            detail="Este jugador no tiene FCM tokens válidos guardados",
        )

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
    # (opcional) acá podrías validar rol admin, etc.
    tokens = db.query(PushToken).filter(PushToken.jugador_id == payload.jugador_id).all()
    if not tokens:
        raise HTTPException(status_code=404, detail="Ese jugador no tiene token registrado")

    # Filtramos tokens inválidos (por si quedó basura vieja)
    token_list = []
    for t in tokens:
        fcm = (t.fcm_token or "").strip()
        if not fcm or len(fcm) < 20:
            continue
        if _is_probably_jwt(fcm):
            continue
        token_list.append(fcm)

    if not token_list:
        raise HTTPException(
            status_code=400,
            detail="Ese jugador no tiene FCM tokens válidos guardados",
        )

    result = send_push_to_tokens(
        token_list,
        title=payload.title,
        body=payload.body,
        data=payload.data or {"type": "test", "scope": "jugador", "from": str(jugador.id)},
    )
    return {"to_jugador_id": payload.jugador_id, **result}
