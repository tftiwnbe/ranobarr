from datetime import datetime, timezone
from uuid import uuid4

from sqlmodel import Field, SQLModel


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Artifact(SQLModel, table=True):
    id: str = Field(default_factory=lambda: str(uuid4()), primary_key=True)
    book_id: str = Field(foreign_key="book.id", index=True)
    format: str = Field(index=True)
    relative_path: str
    chapter_count: int = 0
    file_size_bytes: int = 0
    created_at: datetime = Field(default_factory=utcnow)
