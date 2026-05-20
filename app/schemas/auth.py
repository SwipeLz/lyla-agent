from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class LoginRequest(BaseModel):
    username: str
    password: str


class MeResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    username: str
    expires_at: datetime
