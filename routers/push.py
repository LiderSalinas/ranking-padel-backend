# routers/push.py
from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from database import get_db
from core.security import get_current_jugador
import models
from schemas.push import PushTokenIn, PushTokenOut

router = APIRouter(prefix="/push", tags=["Push"])

@router.post("/token", response_model=PushTokenOut)
def save_push_token(
    payload: PushTokenIn,
    request: Request,
    db: Session = Depends(get_db),
    jugador=Depends(get_current_jugador),
):
    """
    Guarda el token FCM asociado al jugador autenticado.
    """
    ua = payload.user_agent or request.headers.get("user-agent")

    # Evita duplicados por UniqueConstraint
    existing = (
        db.query(models.PushToken)
        .filter(
            models.PushToken.jugador_id == jugador.id,
            models.PushToken.token == payload.token,
        )
        .first()
    )

    if existing:
        # Actualizamos meta si cambió
        existing.platform = payload.platform
        existing.user_agent = ua
        db.commit()
        return {"ok": True}

    row = models.PushToken(
        jugador_id=jugador.id,
        token=payload.token,
        platform=payload.platform,
        user_agent=ua,
    )
    db.add(row)
    db.commit()
    return {"ok": True}
