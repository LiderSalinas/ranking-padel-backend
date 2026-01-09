# schemas/auth.py
from pydantic import BaseModel, EmailStr


class LoginLinkRequest(BaseModel):
    email: EmailStr


class LoginLinkResponse(BaseModel):
    login_url: str
    token: str


class AuthMeResponse(BaseModel):
    id: int
    nombre: str
    apellido: str
    email: EmailStr
    telefono: str | None = None
