from datetime import datetime

from pydantic import BaseModel


class RanobeLibCredentialUpsert(BaseModel):
    access_token: str | None = None
    refresh_token: str | None = None
    expires_at: datetime | None = None


class RanobeLibCredentialView(BaseModel):
    provider: str
    has_access_token: bool
    has_refresh_token: bool
    expires_at: datetime | None
    updated_at: datetime


class RanobeLibCredentialValidation(BaseModel):
    provider: str
    valid: bool
    authenticated: bool
    user_id: str | None = None
    username: str | None = None
    email: str | None = None
    error: str | None = None
