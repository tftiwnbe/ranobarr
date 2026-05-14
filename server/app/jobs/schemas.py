from datetime import datetime

from pydantic import BaseModel


class JobSummary(BaseModel):
    id: str
    type: str
    status: str
    book_id: str | None
    error_message: str | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None


class JobDetail(JobSummary):
    payload_json: str | None
    result_json: str | None
