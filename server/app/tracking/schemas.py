from datetime import datetime

from pydantic import BaseModel, Field


class TrackBookRequest(BaseModel):
    url: str
    branch_mode: str = Field(default="default")
    selected_branch_id: str | None = None


class BuildRequest(BaseModel):
    formats: list[str] = Field(default_factory=lambda: ["manifest", "epub"])


class JobEnqueueResponse(BaseModel):
    job_id: str
    status: str


class BranchSummary(BaseModel):
    id: str
    name: str
    chapter_count: int
    team_names: list[str]
    display: str


class TrackBookResponse(BaseModel):
    book_id: str
    slug: str
    title: str
    author: str | None
    summary: str | None
    cover_url: str | None
    available_chapters: int
    branch_mode: str
    selected_branch_id: str | None
    selected_branch_label: str | None
    branches: list[BranchSummary]
    created_job_id: str


class TrackedBookSummary(BaseModel):
    book_id: str
    slug: str
    title: str
    available_chapters: int
    known_remote_chapters: int
    branch_mode: str
    selected_branch_id: str | None
    selected_branch_label: str | None
    enabled: bool
    last_checked_at: datetime | None
    last_remote_chapter_key: str | None


class ChapterSnapshotSummary(BaseModel):
    chapter_key: str
    volume: str
    number: str
    title: str | None
    branch_id: str | None
    branch_name: str | None
    ordinal_index: int


class TrackedBookDetail(TrackedBookSummary):
    source_url: str
    author: str | None
    summary: str | None
    cover_url: str | None
    snapshots: list[ChapterSnapshotSummary]
