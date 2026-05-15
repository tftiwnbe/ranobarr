from datetime import datetime, timezone
from uuid import uuid4

from sqlmodel import Field, SQLModel


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class JobEvent(SQLModel, table=True):
    id: str = Field(default_factory=lambda: str(uuid4()), primary_key=True)
    job_id: str = Field(foreign_key="jobrecord.id", index=True)
    level: str = Field(index=True)
    event_type: str = Field(index=True)
    message: str
    payload_json: str | None = None
    created_at: datetime = Field(default_factory=utcnow)
