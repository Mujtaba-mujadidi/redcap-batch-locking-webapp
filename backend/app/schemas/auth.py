from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import Role


class LoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=8, max_length=255)


class AuthUserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email: str
    full_name: str | None
    role: Role
    is_active: bool
    is_two_factor_enabled: bool
    created_at: datetime
    updated_at: datetime


class AuthSessionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    expires_at: datetime
    created_at: datetime
    last_seen_at: datetime | None


class AuthenticatedResponse(BaseModel):
    user: AuthUserRead
    session: AuthSessionRead


class LogoutResponse(BaseModel):
    message: str


class LoginContextResponse(BaseModel):
    has_users: bool
    user_count: int
