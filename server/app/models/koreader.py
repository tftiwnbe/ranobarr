from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from sqlmodel import Field, SQLModel


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class KOReaderSyncUser(SQLModel, table=True):
    id: str = Field(default_factory=lambda: str(uuid4()), primary_key=True)
    username: str = Field(index=True, unique=True)
    auth_key: str
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


class KOReaderSyncDocument(SQLModel, table=True):
    id: str = Field(default_factory=lambda: str(uuid4()), primary_key=True)
    user_id: str = Field(foreign_key="koreadersyncuser.id", index=True)
    document_hash: str = Field(index=True)
    title: str | None = None
    author: str | None = None
    linked_book_id: str | None = Field(default=None, foreign_key="book.id", index=True)
    progress: str | None = None
    progress_percent: float | None = None
    device: str | None = None
    device_id: str | None = None
    progress_timestamp: int | None = None
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)
