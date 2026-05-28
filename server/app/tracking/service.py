import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.builds.storage import artifact_file_path, cache_file_path
from app.core.errors import TrackingError
from app.core.jobs import enqueue_job
from app.core.titles import normalize_book_title
from app.models import (
    Artifact,
    Book,
    BookState,
    ChapterContentCache,
    ChapterSnapshot,
    JobEvent,
    JobRecord,
    TrackRule,
)
from app.ranobelib import (
    RanobeLibClient,
    RanobeLibError,
    get_branch_info_for_display,
    get_default_branch_chapters,
    get_formatted_branches_with_teams,
)
from .schemas import (
    BranchSummary,
    NamedTagSummary,
    PreviewBookRequest,
    PreviewBookResponse,
    BranchUpdateRequest,
    ChapterSnapshotSummary,
    TrackBookRequest,
    TrackBookResponse,
    TrackedBookDetail,
    TrackedBookSummary,
)

def utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(slots=True)
class ResolvedBookPayload:
    slug: str
    title: str
    author: str | None
    summary: str | None
    cover_url: str | None
    available_chapters: int
    genres: list[NamedTagSummary]
    tags: list[NamedTagSummary]
    branches: list[BranchSummary]
    selected_branch_label: str | None
    last_remote_chapter_key: str | None


@dataclass(slots=True)
class SelectedChapter:
    chapter_key: str
    volume: str
    number: str
    title: str | None
    branch_id: str | None
    branch_name: str | None
    ordinal_index: int


def chapter_key(volume: Any, number: Any) -> str:
    return f"v{volume or '1'}_ch{number or '0'}"


def branch_id_of(branch: Any) -> str | None:
    if isinstance(branch, dict):
        branch_id = branch.get("branch_id")
        return str(branch_id) if branch_id is not None else "0"
    if branch is None:
        return None
    return str(branch)


def branch_name_of(branch: Any) -> str | None:
    if not isinstance(branch, dict):
        return None

    teams = branch.get("teams") or []
    if teams:
        names = [team.get("name") for team in teams if team.get("name")]
        if names:
            return ", ".join(names)

    team = branch.get("team")
    if isinstance(team, dict) and team.get("name"):
        return str(team["name"])

    return None


def normalize_summary_value(raw_summary: Any) -> str | None:
    if raw_summary is None:
        return None
    if isinstance(raw_summary, str):
        normalized = re.sub(r"\s+", " ", raw_summary).strip()
        return normalized or None
    if isinstance(raw_summary, list):
        normalized = re.sub(r"\s+", " ", " ".join(extract_summary_text(item) for item in raw_summary)).strip()
        return normalized or None
    if isinstance(raw_summary, dict):
        content = raw_summary.get("content")
        if isinstance(content, list):
          normalized = re.sub(r"\s+", " ", " ".join(extract_summary_text(item) for item in content)).strip()
          return normalized or None
    normalized = re.sub(r"\s+", " ", str(raw_summary)).strip()
    return normalized or None


def extract_summary_text(node: Any) -> str:
    if isinstance(node, str):
        return node
    if not isinstance(node, dict):
        return ""

    node_type = node.get("type")
    if node_type == "text":
        return str(node.get("text") or "")
    if node_type == "hardBreak":
        return "\n"

    content = node.get("content")
    if isinstance(content, list):
        parts = [extract_summary_text(item) for item in content]
        delimiter = "\n" if node_type in {"paragraph", "heading", "blockquote", "listItem"} else " "
        return delimiter.join(part for part in parts if part)

    return ""


def slugify_metadata_name(value: str) -> str:
    slug = re.sub(r"[^a-z0-9а-яё]+", "-", value.lower(), flags=re.IGNORECASE)
    return slug.strip("-") or "unknown"


def extract_named_items(raw_items: Any) -> list[NamedTagSummary]:
    items: list[NamedTagSummary] = []
    seen: set[str] = set()
    for raw_item in raw_items or []:
        if isinstance(raw_item, dict):
            name = str(raw_item.get("rus_name") or raw_item.get("name") or "").strip()
        else:
            name = str(raw_item or "").strip()
        if not name:
            continue
        slug = slugify_metadata_name(name)
        if slug in seen:
            continue
        seen.add(slug)
        items.append(NamedTagSummary(name=name, slug=slug))
    return items


def extract_primary_credit(raw_items: Any) -> str | None:
    items = raw_items if isinstance(raw_items, list) else [raw_items]
    for item in items or []:
        if isinstance(item, dict):
            name = str(item.get("rus_name") or item.get("name") or item.get("title") or "").strip()
        else:
            name = str(item or "").strip()
        if name:
            return name
    return None


def resolve_author_label(novel_info: dict[str, Any]) -> str | None:
    author = extract_primary_credit(novel_info.get("authors"))
    if author:
        return author
    return extract_primary_credit(novel_info.get("publisher"))


def serialize_named_items(items: list[NamedTagSummary]) -> str:
    return json.dumps([item.model_dump() for item in items], ensure_ascii=False)


def deserialize_named_items(raw_value: str | None) -> list[NamedTagSummary]:
    if not raw_value:
        return []
    try:
        payload = json.loads(raw_value)
    except json.JSONDecodeError:
        return []
    items: list[NamedTagSummary] = []
    for item in payload or []:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        slug = str(item.get("slug") or slugify_metadata_name(name)).strip()
        if not name:
            continue
        items.append(NamedTagSummary(name=name, slug=slug))
    return items


def serialize_branches(branches: list[BranchSummary]) -> str:
    return json.dumps([branch.model_dump() for branch in branches], ensure_ascii=False)


def deserialize_branches(raw_value: str | None) -> list[BranchSummary]:
    if not raw_value:
        return []
    try:
        payload = json.loads(raw_value)
    except json.JSONDecodeError:
        return []
    branches: list[BranchSummary] = []
    for item in payload or []:
        if not isinstance(item, dict):
            continue
        branch_id = str(item.get("id") or "").strip()
        if not branch_id:
            continue
        branches.append(
            BranchSummary(
                id=branch_id,
                name=str(item.get("name") or "").strip(),
                chapter_count=int(item.get("chapter_count") or 0),
                team_names=[str(name) for name in item.get("team_names") or [] if str(name).strip()],
                display=str(item.get("display") or item.get("name") or branch_id).strip(),
            )
        )
    return branches


def find_branch_label(branches: list[BranchSummary], selected_branch_id: str | None) -> str | None:
    if not selected_branch_id:
        return None
    for branch in branches:
        if branch.id == selected_branch_id:
            return branch.display
    return None


def select_chapters_for_rule(
    chapters_data: list[dict[str, Any]],
    *,
    branch_mode: str,
    selected_branch_id: str | None,
) -> list[SelectedChapter]:
    if branch_mode == "default":
        selected_rows = get_default_branch_chapters(chapters_data)
        return [
            SelectedChapter(
                chapter_key=chapter_key(item["chapter"].get("volume"), item["chapter"].get("number")),
                volume=str(item["chapter"].get("volume", "1")),
                number=str(item["chapter"].get("number", "0")),
                title=item["chapter"].get("name"),
                branch_id=branch_id_of(item["branch"]),
                branch_name=branch_name_of(item["branch"]),
                ordinal_index=int(item["chapter"].get("index", 0)),
            )
            for item in selected_rows
        ]

    selected: list[SelectedChapter] = []
    for chapter in chapters_data:
        matched_branch = None
        if selected_branch_id:
            for branch in chapter.get("branches", []):
                if branch_id_of(branch) == selected_branch_id:
                    matched_branch = branch
                    break
            if matched_branch is None:
                continue

        selected.append(
            SelectedChapter(
                chapter_key=chapter_key(chapter.get("volume"), chapter.get("number")),
                volume=str(chapter.get("volume", "1")),
                number=str(chapter.get("number", "0")),
                title=chapter.get("name"),
                branch_id=branch_id_of(matched_branch),
                branch_name=branch_name_of(matched_branch),
                ordinal_index=int(chapter.get("index", 0)),
            )
        )

    selected.sort(key=lambda chapter: chapter.ordinal_index)
    return selected


async def resolve_remote_book(
    client: RanobeLibClient,
    request: TrackBookRequest | PreviewBookRequest,
) -> ResolvedBookPayload:
    slug = client.extract_slug_from_url(request.url)
    if not slug:
        raise TrackingError("Unsupported RanobeLib URL format")

    try:
        novel_info = await client.get_novel_info(slug)
        chapters_data = await client.get_novel_chapters(slug)
    except RanobeLibError as exc:
        raise TrackingError(str(exc)) from exc

    if not novel_info.get("id"):
        raise TrackingError("RanobeLib metadata is unavailable for this title")

    title = normalize_book_title(
        novel_info.get("rus_name")
        or novel_info.get("eng_name")
        or novel_info.get("name")
        or slug
    )
    author = resolve_author_label(novel_info)

    cover = novel_info.get("cover") or {}
    cover_url = cover.get("default") or cover.get("thumbnail") or cover.get("md")

    branch_map = get_formatted_branches_with_teams(novel_info, chapters_data)
    branch_list = [
        BranchSummary(
            id=branch["id"],
            name=branch["name"],
            chapter_count=branch["chapter_count"],
            team_names=branch["team_names"],
            display=get_branch_info_for_display(branch),
        )
        for branch in sorted(branch_map.values(), key=lambda item: item["chapter_count"], reverse=True)
    ]

    selected_branch_id = getattr(request, "selected_branch_id", None)
    selected_branch_label = find_branch_label(branch_list, selected_branch_id)

    branch_mode = getattr(request, "branch_mode", "default")
    latest_key = None
    if chapters_data:
        selected_rows = select_chapters_for_rule(
            chapters_data,
            branch_mode=branch_mode,
            selected_branch_id=selected_branch_id,
        )
        if selected_rows:
            latest_key = selected_rows[-1].chapter_key

    return ResolvedBookPayload(
        slug=slug,
        title=title,
        author=author,
        summary=normalize_summary_value(novel_info.get("summary")),
        cover_url=cover_url,
        available_chapters=len(chapters_data),
        genres=extract_named_items(novel_info.get("genres")),
        tags=extract_named_items(novel_info.get("tags")),
        branches=branch_list,
        selected_branch_label=selected_branch_label,
        last_remote_chapter_key=latest_key,
    )


async def preview_remote_book(
    client: RanobeLibClient,
    request: PreviewBookRequest,
) -> PreviewBookResponse:
    resolved = await resolve_remote_book(client, request)
    return PreviewBookResponse(
        slug=resolved.slug,
        title=resolved.title,
        author=resolved.author,
        summary=resolved.summary,
        cover_url=resolved.cover_url,
        available_chapters=resolved.available_chapters,
        branches=resolved.branches,
        genres=resolved.genres,
        tags=resolved.tags,
    )


async def track_book(
    session: AsyncSession,
    client: RanobeLibClient,
    request: TrackBookRequest,
) -> TrackBookResponse:
    resolved = await resolve_remote_book(client, request)

    result = await session.exec(select(Book).where(Book.slug == resolved.slug))
    book = result.one_or_none()
    if book is None:
        book = Book(
            slug=resolved.slug,
            source_url=request.url,
            title=resolved.title,
            author=resolved.author,
            cover_url=resolved.cover_url,
            summary=resolved.summary,
            genres_json=serialize_named_items(resolved.genres),
            tags_json=serialize_named_items(resolved.tags),
            branches_json=serialize_branches(resolved.branches),
            available_chapters=resolved.available_chapters,
        )
        session.add(book)
        await session.commit()
        await session.refresh(book)
    else:
        book.source_url = request.url
        book.title = resolved.title
        book.author = resolved.author
        book.cover_url = resolved.cover_url
        book.summary = resolved.summary
        book.genres_json = serialize_named_items(resolved.genres)
        book.tags_json = serialize_named_items(resolved.tags)
        book.branches_json = serialize_branches(resolved.branches)
        book.available_chapters = resolved.available_chapters
        session.add(book)
        await session.commit()
        await session.refresh(book)

    track_rule_result = await session.exec(select(TrackRule).where(TrackRule.book_id == book.id))
    track_rule = track_rule_result.one_or_none()
    if track_rule is None:
        track_rule = TrackRule(book_id=book.id)

    track_rule.enabled = True
    track_rule.branch_mode = request.branch_mode
    track_rule.selected_branch_id = request.selected_branch_id
    track_rule.selected_branch_label = resolved.selected_branch_label
    session.add(track_rule)

    state_result = await session.exec(select(BookState).where(BookState.book_id == book.id))
    state = state_result.one_or_none()
    if state is None:
        state = BookState(book_id=book.id)
    state.last_remote_chapter_key = resolved.last_remote_chapter_key
    session.add(state)
    await session.commit()

    job = await enqueue_job(
        session,
        job_type="check_updates",
        book_id=book.id,
        payload={
            "slug": resolved.slug,
            "branch_mode": request.branch_mode,
            "selected_branch_id": request.selected_branch_id,
        },
    )

    return TrackBookResponse(
        book_id=book.id,
        slug=resolved.slug,
        title=normalize_book_title(resolved.title),
        author=resolved.author,
        summary=resolved.summary,
        cover_url=resolved.cover_url,
        available_chapters=resolved.available_chapters,
        genres=resolved.genres,
        tags=resolved.tags,
        branch_mode=track_rule.branch_mode,
        selected_branch_id=track_rule.selected_branch_id,
        selected_branch_label=track_rule.selected_branch_label,
        branches=resolved.branches,
        created_job_id=job.job_id,
    )


async def list_tracked_books(session: AsyncSession) -> list[TrackedBookSummary]:
    query = (
        select(Book, TrackRule, BookState)
        .join(TrackRule, TrackRule.book_id == Book.id)
        .join(BookState, BookState.book_id == Book.id)
        .order_by(Book.created_at.desc())
    )
    result = await session.exec(query)
    rows = result.all()
    return [
        TrackedBookSummary(
            book_id=book.id,
            slug=book.slug,
            title=normalize_book_title(book.title),
            author=book.author,
            cover_url=book.cover_url,
            available_chapters=book.available_chapters,
            known_remote_chapters=await count_chapter_snapshots(session, book.id),
            genres=deserialize_named_items(book.genres_json),
            tags=deserialize_named_items(book.tags_json),
            branch_mode=rule.branch_mode,
            selected_branch_id=rule.selected_branch_id,
            selected_branch_label=rule.selected_branch_label,
            branches=deserialize_branches(book.branches_json),
            enabled=rule.enabled,
            last_checked_at=state.last_checked_at,
            last_remote_chapter_key=state.last_remote_chapter_key,
        )
        for book, rule, state in rows
    ]


async def get_tracked_book_detail(session: AsyncSession, book_id: str) -> TrackedBookDetail | None:
    query = (
        select(Book, TrackRule, BookState)
        .join(TrackRule, TrackRule.book_id == Book.id)
        .join(BookState, BookState.book_id == Book.id)
        .where(Book.id == book_id)
    )
    result = await session.exec(query)
    row = result.one_or_none()
    if row is None:
        return None

    book, rule, state = row
    snapshots_result = await session.exec(
        select(ChapterSnapshot)
        .where(ChapterSnapshot.book_id == book.id)
        .order_by(ChapterSnapshot.ordinal_index.asc())
    )
    snapshots = snapshots_result.all()

    return TrackedBookDetail(
        book_id=book.id,
        slug=book.slug,
        title=normalize_book_title(book.title),
        source_url=book.source_url,
        author=book.author,
        summary=book.summary,
        cover_url=book.cover_url,
        available_chapters=book.available_chapters,
        known_remote_chapters=len(snapshots),
        genres=deserialize_named_items(book.genres_json),
        tags=deserialize_named_items(book.tags_json),
        branch_mode=rule.branch_mode,
        selected_branch_id=rule.selected_branch_id,
        selected_branch_label=rule.selected_branch_label,
        branches=deserialize_branches(book.branches_json),
        enabled=rule.enabled,
        last_checked_at=state.last_checked_at,
        last_remote_chapter_key=state.last_remote_chapter_key,
        snapshots=[
            ChapterSnapshotSummary(
                chapter_key=snapshot.chapter_key,
                volume=snapshot.volume,
                number=snapshot.number,
                title=snapshot.title,
                branch_id=snapshot.branch_id,
                branch_name=snapshot.branch_name,
                ordinal_index=snapshot.ordinal_index,
            )
            for snapshot in snapshots
        ],
    )


async def count_chapter_snapshots(session: AsyncSession, book_id: str) -> int:
    result = await session.exec(select(ChapterSnapshot).where(ChapterSnapshot.book_id == book_id))
    return len(result.all())


async def process_check_updates_job(
    session: AsyncSession,
    client: RanobeLibClient,
    job: JobRecord,
    event_logger=None,
) -> dict[str, Any]:
    if not job.book_id:
        raise TrackingError("Update-check job is missing a book_id")

    book = await session.get(Book, job.book_id)
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

    novel_info = await client.get_novel_info(book.slug)
    chapters_data = await client.get_novel_chapters(book.slug)
    if event_logger:
        await event_logger(
            level="info",
            event_type="tracking.remote_fetched",
            message="Fetched remote chapter list",
            payload={"remote_chapter_count": len(chapters_data)},
        )
    selected_chapters = select_chapters_for_rule(
        chapters_data,
        branch_mode=rule.branch_mode,
        selected_branch_id=rule.selected_branch_id,
    )
    branch_map = get_formatted_branches_with_teams(novel_info, chapters_data)
    branch_list = [
        BranchSummary(
            id=branch["id"],
            name=branch["name"],
            chapter_count=branch["chapter_count"],
            team_names=branch["team_names"],
            display=get_branch_info_for_display(branch),
        )
        for branch in sorted(branch_map.values(), key=lambda item: item["chapter_count"], reverse=True)
    ]

    snapshots_result = await session.exec(select(ChapterSnapshot).where(ChapterSnapshot.book_id == book.id))
    existing_snapshots = {snapshot.chapter_key: snapshot for snapshot in snapshots_result.all()}
    remote_keys = {chapter.chapter_key for chapter in selected_chapters}
    existing_keys = set(existing_snapshots.keys())

    new_keys = sorted(remote_keys - existing_keys)
    removed_keys = sorted(existing_keys - remote_keys)
    if event_logger:
        await event_logger(
            level="info",
            event_type="tracking.snapshot_diff",
            message="Computed chapter snapshot diff",
            payload={
                "selected_chapter_count": len(selected_chapters),
                "new_chapter_count": len(new_keys),
                "removed_chapter_count": len(removed_keys),
            },
        )

    for chapter in selected_chapters:
        snapshot = existing_snapshots.get(chapter.chapter_key)
        if snapshot is None:
            snapshot = ChapterSnapshot(
                book_id=book.id,
                chapter_key=chapter.chapter_key,
                volume=chapter.volume,
                number=chapter.number,
            )

        snapshot.title = chapter.title
        snapshot.branch_id = chapter.branch_id
        snapshot.branch_name = chapter.branch_name
        snapshot.ordinal_index = chapter.ordinal_index
        snapshot.updated_at = utcnow()
        session.add(snapshot)

    for removed_key in removed_keys:
        await session.delete(existing_snapshots[removed_key])

    now = utcnow()
    latest_remote_key = selected_chapters[-1].chapter_key if selected_chapters else None
    author = resolve_author_label(novel_info)
    cover = novel_info.get("cover") or {}
    book.available_chapters = len(selected_chapters)
    book.title = normalize_book_title(
        novel_info.get("rus_name")
        or novel_info.get("eng_name")
        or novel_info.get("name")
        or book.title
    )
    book.author = author
    book.cover_url = cover.get("default") or cover.get("thumbnail") or cover.get("md")
    book.summary = normalize_summary_value(novel_info.get("summary"))
    book.genres_json = serialize_named_items(extract_named_items(novel_info.get("genres")))
    book.tags_json = serialize_named_items(extract_named_items(novel_info.get("tags")))
    book.branches_json = serialize_branches(branch_list)
    book.updated_at = now
    state.last_remote_chapter_key = latest_remote_key
    state.last_checked_at = now
    state.updated_at = now
    state.last_error = None
    session.add(book)
    session.add(state)
    await session.commit()

    return {
        "book_id": book.id,
        "slug": book.slug,
        "selected_chapter_count": len(selected_chapters),
        "new_chapter_count": len(new_keys),
        "new_chapter_keys": new_keys,
        "removed_chapter_keys": removed_keys,
        "latest_remote_chapter_key": latest_remote_key,
        "build_needed": bool(
            latest_remote_key
            and (
                latest_remote_key != state.last_built_chapter_key
                or bool(new_keys)
                or bool(removed_keys)
            )
        ),
    }


async def delete_tracked_book(session: AsyncSession, book_id: str) -> bool:
    book = await session.get(Book, book_id)
    if book is None:
        return False

    artifacts_result = await session.exec(select(Artifact).where(Artifact.book_id == book_id))
    artifacts = artifacts_result.all()
    for artifact in artifacts:
        artifact_file_path(artifact.relative_path).unlink(missing_ok=True)
        await session.delete(artifact)

    cache_result = await session.exec(select(ChapterContentCache).where(ChapterContentCache.book_id == book_id))
    cache_entries = cache_result.all()
    for cache_entry in cache_entries:
        cache_file_path(cache_entry.relative_path).unlink(missing_ok=True)
        await session.delete(cache_entry)

    snapshots_result = await session.exec(select(ChapterSnapshot).where(ChapterSnapshot.book_id == book_id))
    for snapshot in snapshots_result.all():
        await session.delete(snapshot)

    state_result = await session.exec(select(BookState).where(BookState.book_id == book_id))
    state = state_result.one_or_none()
    if state is not None:
        await session.delete(state)

    track_rule_result = await session.exec(select(TrackRule).where(TrackRule.book_id == book_id))
    track_rule = track_rule_result.one_or_none()
    if track_rule is not None:
        await session.delete(track_rule)

    job_result = await session.exec(select(JobRecord).where(JobRecord.book_id == book_id))
    jobs = job_result.all()
    if jobs:
        job_ids = [job.id for job in jobs]
        job_events_result = await session.exec(select(JobEvent).where(JobEvent.job_id.in_(job_ids)))
        for event in job_events_result.all():
            await session.delete(event)
        for job in jobs:
            await session.delete(job)

    await session.delete(book)
    await session.commit()

    for relative_dir in (
        Path("artifacts") / book_id,
        Path("cache") / "chapters" / book_id,
    ):
        absolute_dir = cache_file_path(str(relative_dir))
        try:
            absolute_dir.rmdir()
        except OSError:
            pass

    return True


async def update_tracked_book_branch(
    session: AsyncSession,
    *,
    book_id: str,
    request: BranchUpdateRequest,
) -> tuple[TrackedBookSummary, JobRecord]:
    detail = await get_tracked_book_detail(session, book_id)
    if detail is None:
        raise TrackingError("Tracked book not found")

    track_rule_result = await session.exec(select(TrackRule).where(TrackRule.book_id == book_id))
    track_rule = track_rule_result.one_or_none()
    if track_rule is None:
        raise TrackingError("Track rule not found")

    branches = detail.branches
    selected_branch_label = find_branch_label(branches, request.selected_branch_id)
    if request.selected_branch_id and selected_branch_label is None:
        raise TrackingError("Selected branch is unavailable for this title")

    track_rule.branch_mode = "selected" if request.selected_branch_id else "default"
    track_rule.selected_branch_id = request.selected_branch_id
    track_rule.selected_branch_label = selected_branch_label
    track_rule.updated_at = utcnow()
    session.add(track_rule)
    await session.commit()

    job = await enqueue_job(
        session,
        job_type="check_updates",
        book_id=book_id,
        payload={
            "slug": detail.slug,
            "branch_mode": track_rule.branch_mode,
            "selected_branch_id": track_rule.selected_branch_id,
        },
    )
    updated = await get_tracked_book_detail(session, book_id)
    assert updated is not None
    return TrackedBookSummary(
        book_id=updated.book_id,
        slug=updated.slug,
        title=updated.title,
        author=updated.author,
        cover_url=updated.cover_url,
        available_chapters=updated.available_chapters,
        known_remote_chapters=updated.known_remote_chapters,
        genres=updated.genres,
        tags=updated.tags,
        branch_mode=updated.branch_mode,
        selected_branch_id=updated.selected_branch_id,
        selected_branch_label=updated.selected_branch_label,
        branches=updated.branches,
        enabled=updated.enabled,
        last_checked_at=updated.last_checked_at,
        last_remote_chapter_key=updated.last_remote_chapter_key,
    ), job
