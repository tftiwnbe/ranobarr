from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4

from sqlmodel import Field, SQLModel


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Book(SQLModel, table=True):
    id: str = Field(default_factory=lambda: str(uuid4()), primary_key=True)
    slug: str = Field(index=True, unique=True)
    source_url: str
    title: str
    author: str | None = None
    cover_url: str | None = None
    summary: str | None = None
    status: str | None = None
    genres_json: str | None = None
    tags_json: str | None = None
    opds_visible_genres_json: str | None = None
    opds_visible_tags_json: str | None = None
    branches_json: str | None = None
    is_favorite: bool = False
    is_current: bool = False
    rating: int | None = None
    comment: str | None = None
    available_chapters: int = 0
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


class TrackRule(SQLModel, table=True):
    id: str = Field(default_factory=lambda: str(uuid4()), primary_key=True)
    book_id: str = Field(foreign_key="book.id", unique=True, index=True)
    enabled: bool = True
    branch_mode: str = "default"
    selected_branch_id: str | None = None
    selected_branch_label: str | None = None
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


class BookState(SQLModel, table=True):
    id: str = Field(default_factory=lambda: str(uuid4()), primary_key=True)
    book_id: str = Field(foreign_key="book.id", unique=True, index=True)
    last_remote_chapter_key: str | None = None
    last_built_chapter_key: str | None = None
    last_checked_at: Optional[datetime] = None
    last_built_at: Optional[datetime] = None
    last_downloaded_at: Optional[datetime] = None
    last_error: str | None = None
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


class UserCollection(SQLModel, table=True):
    id: str = Field(default_factory=lambda: str(uuid4()), primary_key=True)
    slug: str = Field(index=True, unique=True)
    name: str
    description: str | None = None
    sort_order: int = 0
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


class CollectionBook(SQLModel, table=True):
    id: str = Field(default_factory=lambda: str(uuid4()), primary_key=True)
    collection_id: str = Field(foreign_key="usercollection.id", index=True)
    book_id: str = Field(foreign_key="book.id", index=True)
    created_at: datetime = Field(default_factory=utcnow)


class AppSetting(SQLModel, table=True):
    id: str = Field(default_factory=lambda: str(uuid4()), primary_key=True)
    key: str = Field(index=True, unique=True)
    value_json: str
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)
