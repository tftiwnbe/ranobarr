from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4

from sqlmodel import Field, SQLModel


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class JobRecord(SQLModel, table=True):
    id: str = Field(default_factory=lambda: str(uuid4()), primary_key=True)
    type: str = Field(index=True)
    status: str = Field(index=True)
    book_id: str | None = Field(default=None, foreign_key="book.id", index=True)
    payload_json: str | None = None
    result_json: str | None = None
    error_message: str | None = None
    created_at: datetime = Field(default_factory=utcnow)
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
