from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.database import get_database_session
from app.ranobelib import RanobeLibClient
from .schemas import TrackBookRequest, TrackBookResponse, TrackedBookSummary
from .service import TrackingError, list_tracked_books, track_book

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
