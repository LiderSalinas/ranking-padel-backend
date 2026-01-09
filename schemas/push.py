# schemas/push.py
from pydantic import BaseModel, Field


class PushTokenUpsert(BaseModel):
    fcm_token: str = Field(..., min_length=20)

class PushTokenResponse(BaseModel):
    ok: bool
    jugador_id: int
