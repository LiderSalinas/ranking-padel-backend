# routers/auth.py
import os
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from database import get_db
from models import Jugador
from core.security import (
    create_access_token,
    ACCESS_TOKEN_EXPIRE_MINUTES,
    get_current_jugador,
)
from schemas.auth import LoginLinkRequest, LoginLinkResponse, AuthMeResponse

router = APIRouter(prefix="/auth", tags=["Auth"])

FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:5173").rstrip("/")


@router.post("/login-link", response_model=LoginLinkResponse, status_code=status.HTTP_200_OK)
def generar_login_link(payload: LoginLinkRequest, db: Session = Depends(get_db)):
    jugador = db.query(Jugador).filter(Jugador.email == payload.email).first()

    if not jugador:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No existe un jugador con ese email.",
        )

    token_data = {"sub": str(jugador.id), "email": jugador.email, "type": "magic_link"}

    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    token = create_access_token(data=token_data, expires_delta=access_token_expires)

    # ✅ ahora sale apuntando al front real
    login_url = f"{FRONTEND_URL}/auth/magic?token={token}"

    return LoginLinkResponse(login_url=login_url, token=token)


@router.get("/me", response_model=AuthMeResponse)
def auth_me(jugador_actual: Jugador = Depends(get_current_jugador)):
    return AuthMeResponse(
        id=jugador_actual.id,
        nombre=jugador_actual.nombre,
        apellido=jugador_actual.apellido,
        email=jugador_actual.email,
        telefono=jugador_actual.telefono,
    )
