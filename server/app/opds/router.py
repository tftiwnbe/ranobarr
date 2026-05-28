from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from fastapi.responses import FileResponse
from sqlmodel.ext.asyncio.session import AsyncSession

from app.artifacts.service import artifact_download_filename, artifact_media_type, latest_artifact_for_book
from app.builds.assets import ensure_binary_assets_cached
from app.builds.storage import artifact_file_path, asset_file_path
from app.core.database import get_database_session
from app.models import Book
from .service import (
    build_book_detail_feed,
    build_books_feed,
    build_opensearch_description,
    build_root_feed,
    get_downloadable_book_record,
    list_downloadable_books,
)

router = APIRouter(prefix="/opds", tags=["opds"])


@router.get("", name="opds_root")
async def opds_root(
    request: Request,
    session: AsyncSession = Depends(get_database_session),
) -> Response:
    records, total_count = await list_downloadable_books(
        session,
        page=1,
        page_size=20,
        sort="updated",
    )
    payload = build_root_feed(
        request,
        downloadable_count=total_count,
        latest_updated_at=max((record.updated_at for record in records), default=None),
    )
    return Response(content=payload, media_type="application/atom+xml;profile=opds-catalog;kind=navigation")


@router.get("/opensearch.xml", name="opds_opensearch")
async def opds_opensearch(request: Request) -> Response:
    payload = build_opensearch_description(request)
    return Response(content=payload, media_type="application/opensearchdescription+xml")


@router.get("/books", name="opds_books_feed")
async def opds_books_feed(
    request: Request,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=50),
    sort: str = Query(default="updated", pattern="^(updated|title)$"),
    session: AsyncSession = Depends(get_database_session),
) -> Response:
    records, total_count = await list_downloadable_books(
        session,
        page=page,
        page_size=page_size,
        sort=sort,
    )
    self_href = str(request.url)
    payload = build_books_feed(
        request,
        title="Ranobarr Books",
        feed_id=str(request.url_for("opds_books_feed")),
        records=records,
        total_count=total_count,
        page=page,
        page_size=page_size,
        self_href=self_href,
        start_href=str(request.url_for("opds_root")),
    )
    return Response(content=payload, media_type="application/atom+xml;profile=opds-catalog;kind=acquisition")


@router.get("/search", name="opds_search_feed")
async def opds_search_feed(
    request: Request,
    q: str = Query(default=""),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=50),
    session: AsyncSession = Depends(get_database_session),
) -> Response:
    records, total_count = await list_downloadable_books(
        session,
        page=page,
        page_size=page_size,
        sort="title",
        query=q,
    )
    payload = build_books_feed(
        request,
        title=f"Search: {q or 'all books'}",
        feed_id=str(request.url),
        records=records,
        total_count=total_count,
        page=page,
        page_size=page_size,
        self_href=str(request.url),
        start_href=str(request.url_for("opds_root")),
    )
    return Response(content=payload, media_type="application/atom+xml;profile=opds-catalog;kind=acquisition")


@router.get("/books/{book_id}", name="opds_book_feed")
async def opds_book_feed(
    book_id: str,
    request: Request,
    session: AsyncSession = Depends(get_database_session),
) -> Response:
    record = await get_downloadable_book_record(session, book_id=book_id)
    if record is None:
        book = await session.get(Book, book_id)
        if book is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tracked book not found")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="EPUB artifact not found")

    payload = build_book_detail_feed(request, record=record)
    return Response(content=payload, media_type="application/atom+xml;profile=opds-catalog;kind=acquisition")


@router.get("/books/{book_id}/cover", name="opds_cover")
async def opds_cover(
    book_id: str,
    session: AsyncSession = Depends(get_database_session),
):
    book = await session.get(Book, book_id)
    if book is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tracked book not found")
    if not book.cover_url:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cover not available")

    assets = await ensure_binary_assets_cached(session, [book.cover_url])
    cached_asset = assets.get(book.cover_url)
    if cached_asset is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cover could not be fetched")

    file_path = asset_file_path(cached_asset.relative_path)
    if not file_path.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cached cover file not found")

    return FileResponse(path=file_path, media_type=cached_asset.media_type, filename=cached_asset.original_name)


@router.get("/books/{book_id}/acquire/epub", name="opds_acquire_epub")
async def opds_acquire_epub(
    book_id: str,
    session: AsyncSession = Depends(get_database_session),
):
    book = await session.get(Book, book_id)
    if book is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tracked book not found")

    artifact = await latest_artifact_for_book(session, book_id=book_id, format_name="epub")
    if artifact is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="EPUB artifact not found")

    file_path = artifact_file_path(artifact.relative_path)
    if not file_path.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Artifact file not found")

    return FileResponse(
        path=file_path,
        media_type=artifact_media_type(artifact),
        filename=artifact_download_filename(book, artifact),
    )
