# schemas/push.py
from pydantic import BaseModel, Field
from typing import Optional

class PushTokenIn(BaseModel):
    token: str = Field(..., min_length=10)
    platform: Optional[str] = "web"
    user_agent: Optional[str] = None

class PushTokenOut(BaseModel):
    ok: bool
