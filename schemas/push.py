# schemas/push.py
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any

class PushTokenUpsert(BaseModel):
    fcm_token: str = Field(..., min_length=20)

class PushTokenResponse(BaseModel):
    ok: bool
    jugador_id: int
class PushSendToJugador(BaseModel):
    jugador_id: int
    title: str = Field(default="Ranking Pádel")
    body: str = Field(default="Notificación de prueba")
    data: Optional[Dict[str, Any]] = None


class PushSendToMe(BaseModel):
    title: str = Field(default="Ranking Pádel")
    body: str = Field(default="Notificación de prueba")
    data: Optional[Dict[str, Any]] = None
