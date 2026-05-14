from dataclasses import dataclass
from typing import Any

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.jobs import EnqueueJobResult, enqueue_job
from app.models import Book, BookState, TrackRule
from app.ranobelib import (
    RanobeLibClient,
    RanobeLibError,
    get_branch_info_for_display,
    get_default_branch_chapters,
    get_formatted_branches_with_teams,
)
from .schemas import BranchSummary, TrackBookRequest, TrackBookResponse, TrackedBookSummary


class TrackingError(RuntimeError):
    pass


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


def chapter_key(volume: Any, number: Any) -> str:
    return f"v{volume or '1'}_ch{number or '0'}"


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
        if request.branch_mode == "default":
            default_set = get_default_branch_chapters(chapters_data)
            chapter_items = [item["chapter"] for item in default_set]
        elif request.selected_branch_id:
            chapter_items = [
                chapter
                for chapter in chapters_data
                if any(
                    (
                        isinstance(branch, dict)
                        and str(branch.get("branch_id") if branch.get("branch_id") is not None else "0")
                        == request.selected_branch_id
                    )
                    or (not isinstance(branch, dict) and str(branch) == request.selected_branch_id)
                    for branch in chapter.get("branches", [])
                )
            ]
        else:
            chapter_items = chapters_data

        if chapter_items:
            latest = chapter_items[-1]
            latest_key = chapter_key(latest.get("volume"), latest.get("number"))

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
            branch_mode=rule.branch_mode,
            selected_branch_id=rule.selected_branch_id,
            selected_branch_label=rule.selected_branch_label,
            enabled=rule.enabled,
            last_checked_at=state.last_checked_at,
            last_remote_chapter_key=state.last_remote_chapter_key,
        )
        for book, rule, state in rows
    ]
