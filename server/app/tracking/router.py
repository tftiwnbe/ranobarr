from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.jobs import enqueue_job
from app.core.database import get_database_session
from app.ranobelib import RanobeLibClient
from .schemas import TrackBookRequest, TrackBookResponse, TrackedBookDetail, TrackedBookSummary
from .service import TrackingError, get_tracked_book_detail, list_tracked_books, track_book

router = APIRouter(prefix="/api/v1/tracking", tags=["tracking"])


async def get_ranobelib_client() -> RanobeLibClient:
    client = RanobeLibClient()
    try:
        yield client
    finally:
        await client.close()


@router.post("/books", response_model=TrackBookResponse, status_code=status.HTTP_201_CREATED)
async def create_tracked_book(
    request: TrackBookRequest,
    session: AsyncSession = Depends(get_database_session),
    client: RanobeLibClient = Depends(get_ranobelib_client),
) -> TrackBookResponse:
    try:
        return await track_book(session, client, request)
    except TrackingError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.get("/books", response_model=list[TrackedBookSummary])
async def get_tracked_books(
    session: AsyncSession = Depends(get_database_session),
) -> list[TrackedBookSummary]:
    return await list_tracked_books(session)


@router.get("/books/{book_id}", response_model=TrackedBookDetail)
async def get_tracked_book(
    book_id: str,
    session: AsyncSession = Depends(get_database_session),
) -> TrackedBookDetail:
    detail = await get_tracked_book_detail(session, book_id)
    if detail is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tracked book not found")
    return detail


@router.post("/books/{book_id}/check", status_code=status.HTTP_202_ACCEPTED)
async def check_tracked_book_now(
    book_id: str,
    session: AsyncSession = Depends(get_database_session),
) -> dict[str, str]:
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
        },
    )
    return {"job_id": job.job_id, "status": job.status}
