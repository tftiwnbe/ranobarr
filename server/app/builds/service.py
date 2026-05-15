from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.builds.content import NormalizedChapter, load_cached_payload, normalize_cached_payload
from app.builds.epub import build_epub_bytes
from app.builds.storage import (
    artifact_file_path,
    cache_file_path,
    write_artifact_manifest,
    write_chapter_cache,
    write_epub_artifact,
)
from app.config import get_settings
from app.core.errors import TrackingError
from app.models import Artifact, Book, BookState, ChapterContentCache, ChapterSnapshot, TrackRule
from app.ranobelib import RanobeLibClient


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def detect_content_type(content: Any) -> str:
    if isinstance(content, str):
        stripped = content.strip()
        if stripped.startswith("<"):
            return "html"
        return "text"
    if isinstance(content, dict) and content.get("type") == "doc":
        return "doc"
    if isinstance(content, dict) and isinstance(content.get("content"), list):
        return "doc"
    if isinstance(content, list):
        return "doc"
    return "unknown"


def hash_payload(payload: dict[str, Any]) -> str:
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


@dataclass(slots=True)
class CachedChapterResult:
    chapter_key: str
    relative_path: str
    content_hash: str
    content_type: str


@dataclass(slots=True)
class ArtifactWriteResult:
    artifact: Artifact
    file_path: Path


async def build_book_artifact(
    session: AsyncSession,
    client: RanobeLibClient,
    *,
    book_id: str,
) -> dict[str, Any]:
    book = await session.get(Book, book_id)
    if book is None:
        raise TrackingError("Tracked book not found")

    rule_result = await session.exec(select(TrackRule).where(TrackRule.book_id == book.id))
    rule = rule_result.one_or_none()
    if rule is None:
        raise TrackingError("Track rule not found")

    state_result = await session.exec(select(BookState).where(BookState.book_id == book.id))
    state = state_result.one_or_none()
    if state is None:
        state = BookState(book_id=book.id)

    snapshots_result = await session.exec(
        select(ChapterSnapshot)
        .where(ChapterSnapshot.book_id == book.id)
        .order_by(ChapterSnapshot.ordinal_index.asc())
    )
    snapshots = snapshots_result.all()
    if not snapshots:
        raise TrackingError("No chapter snapshots found for this book")

    content_cache_result = await session.exec(
        select(ChapterContentCache).where(ChapterContentCache.book_id == book.id)
    )
    existing_cache = {cache.chapter_key: cache for cache in content_cache_result.all()}

    cached_results: list[CachedChapterResult] = []
    normalized_chapters: list[NormalizedChapter] = []
    fetched_count = 0
    reused_count = 0

    for snapshot in snapshots:
        cache_entry = existing_cache.get(snapshot.chapter_key)
        if cache_entry is not None and cache_file_path(cache_entry.relative_path).is_file():
            reused_count += 1
            cached_results.append(
                CachedChapterResult(
                    chapter_key=snapshot.chapter_key,
                    relative_path=cache_entry.relative_path,
                    content_hash=cache_entry.content_hash,
                    content_type=cache_entry.content_type,
                )
            )
            payload = load_cached_payload(cache_entry.relative_path)
            normalized_chapters.append(
                normalize_cached_payload(payload, content_type=cache_entry.content_type)
            )
            continue

        chapter_data = await client.get_chapter_content(
            book.slug,
            volume=snapshot.volume,
            number=snapshot.number,
            branch_id=snapshot.branch_id,
        )
        payload = {
            "book_id": book.id,
            "chapter_key": snapshot.chapter_key,
            "volume": snapshot.volume,
            "number": snapshot.number,
            "title": snapshot.title,
            "branch_id": snapshot.branch_id,
            "branch_name": snapshot.branch_name,
            "fetched_at": utcnow().isoformat(),
            "content": chapter_data.get("content"),
            "attachments": chapter_data.get("attachments") or [],
        }
        content_type = detect_content_type(payload["content"])
        content_hash = hash_payload(payload)
        relative_path = write_chapter_cache(book.id, snapshot.chapter_key, payload)

        if cache_entry is None:
            cache_entry = ChapterContentCache(
                book_id=book.id,
                chapter_key=snapshot.chapter_key,
                branch_id=snapshot.branch_id,
                content_type=content_type,
                relative_path=relative_path,
                content_hash=content_hash,
            )
        else:
            cache_entry.branch_id = snapshot.branch_id
            cache_entry.content_type = content_type
            cache_entry.relative_path = relative_path
            cache_entry.content_hash = content_hash
            cache_entry.fetched_at = utcnow()
            cache_entry.updated_at = utcnow()

        session.add(cache_entry)
        cached_results.append(
            CachedChapterResult(
                chapter_key=snapshot.chapter_key,
                relative_path=relative_path,
                content_hash=content_hash,
                content_type=content_type,
            )
        )
        normalized_chapters.append(normalize_cached_payload(payload, content_type=content_type))
        fetched_count += 1

    manifest = {
        "book": {
            "id": book.id,
            "slug": book.slug,
            "title": book.title,
            "author": book.author,
        },
        "generated_at": utcnow().isoformat(),
        "chapter_count": len(snapshots),
        "latest_remote_chapter_key": state.last_remote_chapter_key,
        "branch_mode": rule.branch_mode,
        "selected_branch_id": rule.selected_branch_id,
        "chapters": [
            {
                "chapter_key": snapshot.chapter_key,
                "volume": snapshot.volume,
                "number": snapshot.number,
                "title": snapshot.title,
                "branch_id": snapshot.branch_id,
                "branch_name": snapshot.branch_name,
                "cache_path": next(
                    item.relative_path for item in cached_results if item.chapter_key == snapshot.chapter_key
                ),
            }
            for snapshot in snapshots
        ],
    }

    artifact_relative_path = write_artifact_manifest(book.id, manifest)
    manifest_artifact = await create_artifact_record(
        session,
        book_id=book.id,
        format_name="manifest",
        relative_path=artifact_relative_path,
        chapter_count=len(snapshots),
    )

    epub_bytes = await build_epub_bytes(
        identifier=f"ranobarr-{book.id}",
        title=book.title,
        author=book.author,
        summary=book.summary,
        cover_url=book.cover_url,
        chapters=normalized_chapters,
    )
    epub_relative_path = write_epub_artifact(book.id, epub_bytes)
    epub_artifact = await create_artifact_record(
        session,
        book_id=book.id,
        format_name="epub",
        relative_path=epub_relative_path,
        chapter_count=len(normalized_chapters),
    )

    state.last_built_chapter_key = state.last_remote_chapter_key
    state.last_built_at = utcnow()
    state.updated_at = utcnow()
    session.add(state)
    await session.commit()

    return {
        "book_id": book.id,
        "artifact_id": epub_artifact.id,
        "artifact_format": epub_artifact.format,
        "artifact_path": epub_artifact.relative_path,
        "chapter_count": len(snapshots),
        "fetched_chapter_count": fetched_count,
        "reused_cached_chapter_count": reused_count,
        "artifacts": [
            {
                "id": manifest_artifact.id,
                "format": manifest_artifact.format,
                "path": manifest_artifact.relative_path,
            },
            {
                "id": epub_artifact.id,
                "format": epub_artifact.format,
                "path": epub_artifact.relative_path,
            },
        ],
    }
async def create_artifact_record(
    session: AsyncSession,
    *,
    book_id: str,
    format_name: str,
    relative_path: str,
    chapter_count: int,
) -> Artifact:
    artifact_path = artifact_file_path(relative_path)
    artifact_size = artifact_path.stat().st_size if artifact_path.exists() else 0
    artifact = Artifact(
        book_id=book_id,
        format=format_name,
        relative_path=relative_path,
        chapter_count=chapter_count,
        file_size_bytes=artifact_size,
    )
    session.add(artifact)
    await session.flush()
    return artifact
