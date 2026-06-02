from datetime import datetime

from pydantic import BaseModel, Field


class TrackBookRequest(BaseModel):
    url: str
    branch_mode: str = Field(default="default")
    selected_branch_id: str | None = None


class PreviewBookRequest(BaseModel):
    url: str


class BuildRequest(BaseModel):
    formats: list[str] = Field(default_factory=lambda: ["manifest", "epub"])


class JobEnqueueResponse(BaseModel):
    job_id: str
    status: str


class BranchUpdateRequest(BaseModel):
    selected_branch_id: str | None = None


class BranchSummary(BaseModel):
    id: str
    name: str
    chapter_count: int
    team_names: list[str]
    display: str


class NamedTagSummary(BaseModel):
    name: str
    slug: str


class CollectionSummary(BaseModel):
    id: str
    slug: str
    name: str
    description: str | None = None
    sort_order: int = 0
    book_count: int = 0


class PreviewBookResponse(BaseModel):
    slug: str
    title: str
    author: str | None
    summary: str | None
    cover_url: str | None
    available_chapters: int
    branches: list[BranchSummary]
    genres: list[NamedTagSummary]
    tags: list[NamedTagSummary]


class TrackBookResponse(BaseModel):
    book_id: str
    slug: str
    title: str
    author: str | None
    summary: str | None
    cover_url: str | None
    available_chapters: int
    genres: list[NamedTagSummary]
    tags: list[NamedTagSummary]
    branch_mode: str
    selected_branch_id: str | None
    selected_branch_label: str | None
    branches: list[BranchSummary]
    created_job_id: str


class TrackedBookSummary(BaseModel):
    book_id: str
    slug: str
    title: str
    author: str | None
    cover_url: str | None
    is_manual_upload: bool
    available_chapters: int
    known_remote_chapters: int
    genres: list[NamedTagSummary]
    tags: list[NamedTagSummary]
    opds_visible_genres: list[NamedTagSummary]
    opds_visible_tags: list[NamedTagSummary]
    branch_mode: str
    selected_branch_id: str | None
    selected_branch_label: str | None
    branches: list[BranchSummary]
    enabled: bool
    is_favorite: bool = False
    is_current: bool = False
    rating: int | None = None
    comment: str | None = None
    collections: list[CollectionSummary] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime
    last_chapter_added_at: datetime | None
    last_checked_at: datetime | None
    last_downloaded_at: datetime | None = None
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
    summary: str | None
    snapshots: list[ChapterSnapshotSummary]


class BookPreferencesUpdateRequest(BaseModel):
    title: str | None = Field(default=None, max_length=240)
    author: str | None = Field(default=None, max_length=240)
    opds_visible_genre_slugs: list[str] | None = None
    opds_visible_tag_slugs: list[str] | None = None
    is_favorite: bool | None = None
    is_current: bool | None = None
    rating: int | None = Field(default=None, ge=0, le=5)
    comment: str | None = None
    collection_ids: list[str] | None = None


class CollectionCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=500)
    sort_order: int = 0


class CollectionUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=500)
    sort_order: int | None = None


class OpdsMetadataVisibilityResponse(BaseModel):
    genres: list[NamedTagSummary]
    tags: list[NamedTagSummary]
    visible_genre_slugs: list[str]
    visible_tag_slugs: list[str]


class OpdsMetadataVisibilityUpdateRequest(BaseModel):
    visible_genre_slugs: list[str] = Field(default_factory=list)
    visible_tag_slugs: list[str] = Field(default_factory=list)
