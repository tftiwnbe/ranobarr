from datetime import datetime

from pydantic import BaseModel


class ArtifactSummary(BaseModel):
    id: str
    book_id: str
    format: str
    relative_path: str
    chapter_count: int
    file_size_bytes: int
    created_at: datetime
