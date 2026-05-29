from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.database import get_database_session
from app.core.errors import TrackingError
from app.tracking.schemas import CollectionCreateRequest, CollectionSummary, CollectionUpdateRequest

from .service import create_collection, delete_collection, list_collection_summaries, update_collection

router = APIRouter(prefix="/api/v1/library", tags=["library"])


@router.get("/collections", response_model=list[CollectionSummary])
async def get_collections(
    session: AsyncSession = Depends(get_database_session),
) -> list[CollectionSummary]:
    return await list_collection_summaries(session)


@router.post("/collections", response_model=CollectionSummary, status_code=status.HTTP_201_CREATED)
async def create_collection_route(
    request: CollectionCreateRequest,
    session: AsyncSession = Depends(get_database_session),
) -> CollectionSummary:
    try:
        return await create_collection(session, request)
    except TrackingError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.patch("/collections/{collection_id}", response_model=CollectionSummary)
async def update_collection_route(
    collection_id: str,
    request: CollectionUpdateRequest,
    session: AsyncSession = Depends(get_database_session),
) -> CollectionSummary:
    try:
        return await update_collection(session, collection_id=collection_id, request=request)
    except TrackingError as exc:
        status_code = status.HTTP_404_NOT_FOUND if str(exc) == "Collection not found" else status.HTTP_400_BAD_REQUEST
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc


@router.delete("/collections/{collection_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_collection_route(
    collection_id: str,
    session: AsyncSession = Depends(get_database_session),
) -> None:
    if not await delete_collection(session, collection_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Collection not found")
