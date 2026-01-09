# core/security.py
from datetime import datetime, timedelta
from typing import Optional

from fastapi import Depends, HTTPException, status, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from pydantic import BaseModel, ValidationError, EmailStr
from sqlalchemy.orm import Session

from database import get_db
from models import Jugador

# ============================
# Configuración JWT
# ============================

SECRET_KEY = "super-secret-key-cambia-esto"  # si querés, luego lo pasamos a .env
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 * 7  # 7 días

# Esquema de seguridad tipo Bearer (aparece en Swagger con candadito)
bearer_scheme = HTTPBearer(auto_error=True)


class TokenPayload(BaseModel):
    sub: Optional[str] = None      # id del jugador (en texto)
    email: Optional[EmailStr] = None
    type: Optional[str] = None     # "magic_link", etc.
    exp: Optional[int] = None


def create_access_token(
    data: dict,
    expires_delta: Optional[timedelta] = None,
) -> str:
    """
    Crea un JWT con los datos pasados en `data`.
    Siempre agrega el campo `exp`.
    """
    to_encode = data.copy()

    if expires_delta is None:
        expires_delta = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)

    expire = datetime.utcnow() + expires_delta
    to_encode.update({"exp": expire})

    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


def decode_access_token(token: str) -> Optional[TokenPayload]:
    """
    Decodifica el JWT y devuelve un TokenPayload válido
    o None si algo sale mal (token inválido o expirado).
    """
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        token_data = TokenPayload(**payload)
        return token_data
    except (JWTError, ValidationError):
        return None


async def get_current_jugador(
    credentials: HTTPAuthorizationCredentials = Security(bearer_scheme),
    db: Session = Depends(get_db),
) -> Jugador:
    """
    Obtiene el jugador actual en base al token Bearer.
    Se espera que el token tenga al menos el campo `email`.
    """
    token = credentials.credentials

    token_data = decode_access_token(token)
    if token_data is None or token_data.email is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token inválido o expirado.",
        )

    # 🔥 Importante: autenticamos por EMAIL, que viene dentro del token
    jugador = (
        db.query(Jugador)
        .filter(Jugador.email == token_data.email)
        .first()
    )

    if not jugador:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Jugador no encontrado para este token.",
        )

    return jugador
