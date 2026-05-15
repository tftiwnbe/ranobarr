from datetime import datetime, timezone
from uuid import uuid4

from sqlmodel import Field, SQLModel


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class SourceCredential(SQLModel, table=True):
    id: str = Field(default_factory=lambda: str(uuid4()), primary_key=True)
    provider: str = Field(index=True, unique=True)
    access_token: str | None = None
    refresh_token: str | None = None
    expires_at: datetime | None = None
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)
