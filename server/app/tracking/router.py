from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.database import get_database_session
from app.core.errors import TrackingError
from app.core.jobs import enqueue_job
from app.ranobelib import RanobeLibClient
from app.source_auth.service import make_ranobelib_client
from .schemas import (
    BranchUpdateRequest,
    BookPreferencesUpdateRequest,
    BuildRequest,
    JobEnqueueResponse,
    PreviewBookRequest,
    PreviewBookResponse,
    TrackBookRequest,
    TrackBookResponse,
    TrackedBookDetail,
    TrackedBookSummary,
)
from .service import (
    delete_tracked_book,
    get_tracked_book_detail,
    list_tracked_books,
    preview_remote_book,
    track_book,
    import_uploaded_epubs,
    update_book_preferences,
    update_tracked_book_cover,
    update_tracked_book_branch,
)

router = APIRouter(prefix="/api/v1/tracking", tags=["tracking"])


async def get_ranobelib_client() -> RanobeLibClient:
    raise RuntimeError("db-backed dependency required")


async def get_authorized_ranobelib_client(
    session: AsyncSession = Depends(get_database_session),
):
    client = await make_ranobelib_client(session)
    try:
        yield client
    finally:
        await client.close()


@router.post("/books", response_model=TrackBookResponse, status_code=status.HTTP_201_CREATED)
async def create_tracked_book(
    request: TrackBookRequest,
    session: AsyncSession = Depends(get_database_session),
    client: RanobeLibClient = Depends(get_authorized_ranobelib_client),
) -> TrackBookResponse:
    try:
        return await track_book(session, client, request)
    except TrackingError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post("/uploads/epub", response_model=list[TrackedBookSummary], status_code=status.HTTP_201_CREATED)
async def upload_epub_books(
    files: list[UploadFile] = File(...),
    session: AsyncSession = Depends(get_database_session),
) -> list[TrackedBookSummary]:
    if not files:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No EPUB files uploaded")

    try:
        payloads: list[tuple[str, bytes]] = []
        for file in files:
            filename = file.filename or "upload.epub"
            if not filename.lower().endswith(".epub"):
                raise TrackingError(f"Unsupported file type: {filename}")
            payloads.append((filename, await file.read()))
        return await import_uploaded_epubs(session, payloads)
    except TrackingError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post("/preview", response_model=PreviewBookResponse)
async def preview_tracked_book(
    request: PreviewBookRequest,
    client: RanobeLibClient = Depends(get_authorized_ranobelib_client),
) -> PreviewBookResponse:
    try:
        return await preview_remote_book(client, request)
    except TrackingError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.get("/books", response_model=list[TrackedBookSummary])
async def get_tracked_books(
    sort: str = Query(default="title", pattern="^(added|updated|title)$"),
    session: AsyncSession = Depends(get_database_session),
) -> list[TrackedBookSummary]:
    try:
        return await list_tracked_books(session, sort=sort)
    except TrackingError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.get("/books/{book_id}", response_model=TrackedBookDetail)
async def get_tracked_book(
    book_id: str,
    session: AsyncSession = Depends(get_database_session),
) -> TrackedBookDetail:
    detail = await get_tracked_book_detail(session, book_id)
    if detail is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tracked book not found")
    return detail


@router.delete("/books/{book_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_tracked_book_route(
    book_id: str,
    session: AsyncSession = Depends(get_database_session),
) -> None:
    deleted = await delete_tracked_book(session, book_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tracked book not found")


@router.patch("/books/{book_id}/branch", response_model=JobEnqueueResponse, status_code=status.HTTP_202_ACCEPTED)
async def update_tracked_book_branch_selection(
    book_id: str,
    request: BranchUpdateRequest,
    session: AsyncSession = Depends(get_database_session),
) -> JobEnqueueResponse:
    try:
        _, job = await update_tracked_book_branch(session, book_id=book_id, request=request)
    except TrackingError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return JobEnqueueResponse(job_id=job.job_id, status=job.status)


@router.patch("/books/{book_id}/preferences", response_model=TrackedBookDetail)
async def update_tracked_book_preferences(
    book_id: str,
    request: BookPreferencesUpdateRequest,
    session: AsyncSession = Depends(get_database_session),
) -> TrackedBookDetail:
    try:
        return await update_book_preferences(session, book_id=book_id, request=request)
    except TrackingError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post("/books/{book_id}/cover", response_model=TrackedBookDetail)
async def upload_tracked_book_cover(
    book_id: str,
    file: UploadFile = File(...),
    session: AsyncSession = Depends(get_database_session),
) -> TrackedBookDetail:
    try:
        filename = file.filename or "cover"
        media_type = file.content_type or "application/octet-stream"
        return await update_tracked_book_cover(
            session,
            book_id=book_id,
            filename=filename,
            content=await file.read(),
            media_type=media_type,
        )
    except TrackingError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post("/books/{book_id}/check", status_code=status.HTTP_202_ACCEPTED)
async def check_tracked_book_now(
    book_id: str,
    session: AsyncSession = Depends(get_database_session),
) -> JobEnqueueResponse:
    detail = await get_tracked_book_detail(session, book_id)
    if detail is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tracked book not found")

    job = await enqueue_job(
        session,
        job_type="check_updates",
        book_id=book_id,
        payload={
            "slug": detail.slug,
            "branch_mode": detail.branch_mode,
            "selected_branch_id": detail.selected_branch_id,
            "trigger": "manual",
        },
    )
    return JobEnqueueResponse(job_id=job.job_id, status=job.status)


@router.post("/books/{book_id}/build", response_model=JobEnqueueResponse, status_code=status.HTTP_202_ACCEPTED)
async def build_tracked_book_now(
    book_id: str,
    request: BuildRequest,
    session: AsyncSession = Depends(get_database_session),
) -> JobEnqueueResponse:
    detail = await get_tracked_book_detail(session, book_id)
    if detail is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tracked book not found")

    job = await enqueue_job(
        session,
        job_type="build_artifact",
        book_id=book_id,
        payload={
            "slug": detail.slug,
            "branch_mode": detail.branch_mode,
            "selected_branch_id": detail.selected_branch_id,
            "formats": request.formats,
            "trigger": "manual",
        },
    )
    return JobEnqueueResponse(job_id=job.job_id, status=job.status)
