from __future__ import annotations

import re
import unicodedata
from pathlib import Path
from typing import Iterable

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models import Artifact, Book

_INVALID_FILENAME_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_WHITESPACE = re.compile(r"\s+")


def artifact_media_type(artifact: Artifact) -> str:
    if artifact.format == "epub":
        return "application/epub+zip"
    if artifact.format == "manifest":
        return "application/json"
    return "application/octet-stream"


def sanitize_filename_component(value: str, fallback: str = "book") -> str:
    normalized = unicodedata.normalize("NFKC", value).strip()
    normalized = _INVALID_FILENAME_CHARS.sub(" ", normalized)
    normalized = _WHITESPACE.sub(" ", normalized).strip(" .")
    return normalized[:120] or fallback


def artifact_download_filename(book: Book, artifact: Artifact) -> str:
    stem = sanitize_filename_component(book.title or book.slug or "book", fallback="book")
    suffix = Path(artifact.relative_path).suffix or f".{artifact.format}"
    if artifact.format == "epub":
        if artifact.chapter_count > 0:
            chapter_label = "chapter" if artifact.chapter_count == 1 else "chapters"
            return f"{stem} ({artifact.chapter_count} {chapter_label}){suffix}"
        return f"{stem}{suffix}"
    if artifact.format == "manifest":
        return f"{stem} manifest{suffix}"
    return f"{stem}{suffix}"


async def latest_artifact_for_book(
    session: AsyncSession,
    *,
    book_id: str,
    format_name: str | None = None,
) -> Artifact | None:
    query = select(Artifact).where(Artifact.book_id == book_id)
    if format_name:
        query = query.where(Artifact.format == format_name)
    query = query.order_by(Artifact.created_at.desc(), Artifact.id.desc())
    result = await session.exec(query)
    return result.first()


async def latest_artifacts_for_books(
    session: AsyncSession,
    *,
    book_ids: Iterable[str],
    format_name: str | None = None,
) -> dict[str, Artifact]:
    ordered_book_ids = [book_id for book_id in book_ids]
    if not ordered_book_ids:
        return {}

    query = select(Artifact).where(Artifact.book_id.in_(ordered_book_ids))
    if format_name:
        query = query.where(Artifact.format == format_name)
    query = query.order_by(Artifact.book_id.asc(), Artifact.created_at.desc(), Artifact.id.desc())
    result = await session.exec(query)

    latest: dict[str, Artifact] = {}
    for artifact in result.all():
        latest.setdefault(artifact.book_id, artifact)
    return latest
