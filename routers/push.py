# routers/push.py
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from database import get_db
from core.security import get_current_jugador
from schemas.push import PushTokenUpsert, PushTokenResponse
from models import PushToken

router = APIRouter(prefix="/push", tags=["Push"])


@router.post(
    "/token",
    response_model=PushTokenResponse,
    status_code=status.HTTP_200_OK,
)
def save_push_token(
    payload: PushTokenUpsert,
    db: Session = Depends(get_db),
    jugador=Depends(get_current_jugador),
):
    token = (payload.fcm_token or "").strip()

    # FCM token suele ser largo; min 20 es ok para validar rápido
    if not token or len(token) < 20:
        raise HTTPException(status_code=400, detail="FCM token inválido")

    existing = db.query(PushToken).filter(PushToken.jugador_id == jugador.id).first()

    if existing:
        existing.fcm_token = token
    else:
        db.add(PushToken(jugador_id=jugador.id, fcm_token=token))

    db.commit()

    return PushTokenResponse(ok=True, jugador_id=jugador.id)
