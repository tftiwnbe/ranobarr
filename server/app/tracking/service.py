import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.jobs import enqueue_job
from app.models import Book, BookState, ChapterSnapshot, JobRecord, TrackRule
from app.ranobelib import (
    RanobeLibClient,
    RanobeLibError,
    get_branch_info_for_display,
    get_default_branch_chapters,
    get_formatted_branches_with_teams,
)
from .schemas import (
    BranchSummary,
    ChapterSnapshotSummary,
    TrackBookRequest,
    TrackBookResponse,
    TrackedBookDetail,
    TrackedBookSummary,
)


class TrackingError(RuntimeError):
    pass


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


async def resolve_remote_book(client: RanobeLibClient, request: TrackBookRequest) -> ResolvedBookPayload:
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

    title = (
        novel_info.get("rus_name")
        or novel_info.get("eng_name")
        or novel_info.get("name")
        or slug
    )
    author = None
    authors = novel_info.get("authors") or []
    if authors:
        author = authors[0].get("name")

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

    selected_branch_label = None
    if request.selected_branch_id:
        for branch in branch_list:
            if branch.id == request.selected_branch_id:
                selected_branch_label = branch.display
                break

    latest_key = None
    if chapters_data:
        selected_rows = select_chapters_for_rule(
            chapters_data,
            branch_mode=request.branch_mode,
            selected_branch_id=request.selected_branch_id,
        )
        if selected_rows:
            latest_key = selected_rows[-1].chapter_key

    return ResolvedBookPayload(
        slug=slug,
        title=title,
        author=author,
        summary=novel_info.get("summary"),
        cover_url=cover_url,
        available_chapters=len(chapters_data),
        branches=branch_list,
        selected_branch_label=selected_branch_label,
        last_remote_chapter_key=latest_key,
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
        title=resolved.title,
        author=resolved.author,
        summary=resolved.summary,
        cover_url=resolved.cover_url,
        available_chapters=resolved.available_chapters,
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
            title=book.title,
            available_chapters=book.available_chapters,
            known_remote_chapters=await count_chapter_snapshots(session, book.id),
            branch_mode=rule.branch_mode,
            selected_branch_id=rule.selected_branch_id,
            selected_branch_label=rule.selected_branch_label,
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
        title=book.title,
        source_url=book.source_url,
        author=book.author,
        summary=book.summary,
        cover_url=book.cover_url,
        available_chapters=book.available_chapters,
        known_remote_chapters=len(snapshots),
        branch_mode=rule.branch_mode,
        selected_branch_id=rule.selected_branch_id,
        selected_branch_label=rule.selected_branch_label,
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

    chapters_data = await client.get_novel_chapters(book.slug)
    selected_chapters = select_chapters_for_rule(
        chapters_data,
        branch_mode=rule.branch_mode,
        selected_branch_id=rule.selected_branch_id,
    )

    snapshots_result = await session.exec(select(ChapterSnapshot).where(ChapterSnapshot.book_id == book.id))
    existing_snapshots = {snapshot.chapter_key: snapshot for snapshot in snapshots_result.all()}
    remote_keys = {chapter.chapter_key for chapter in selected_chapters}
    existing_keys = set(existing_snapshots.keys())

    new_keys = sorted(remote_keys - existing_keys)
    removed_keys = sorted(existing_keys - remote_keys)

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
    book.available_chapters = len(selected_chapters)
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
    }
