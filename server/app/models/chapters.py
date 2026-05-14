from datetime import datetime, timezone
from uuid import uuid4

from sqlmodel import Field, SQLModel


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ChapterSnapshot(SQLModel, table=True):
    id: str = Field(default_factory=lambda: str(uuid4()), primary_key=True)
    book_id: str = Field(foreign_key="book.id", index=True)
    chapter_key: str = Field(index=True)
    volume: str
    number: str
    title: str | None = None
    branch_id: str | None = Field(default=None, index=True)
    branch_name: str | None = None
    ordinal_index: int = 0
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)
