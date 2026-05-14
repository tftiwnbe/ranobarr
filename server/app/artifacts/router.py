from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.builds.service import artifact_file_path
from app.core.database import get_database_session
from app.models import Artifact, Book
from .schemas import ArtifactSummary

router = APIRouter(prefix="/api/v1/artifacts", tags=["artifacts"])


@router.get("", response_model=list[ArtifactSummary])
async def list_artifacts(
    session: AsyncSession = Depends(get_database_session),
) -> list[ArtifactSummary]:
    result = await session.exec(select(Artifact).order_by(Artifact.created_at.desc()))
    artifacts = result.all()
    return [
        ArtifactSummary(
            id=artifact.id,
            book_id=artifact.book_id,
            format=artifact.format,
            relative_path=artifact.relative_path,
            chapter_count=artifact.chapter_count,
            file_size_bytes=artifact.file_size_bytes,
            created_at=artifact.created_at,
        )
        for artifact in artifacts
    ]


@router.get("/books/{book_id}", response_model=list[ArtifactSummary])
async def list_book_artifacts(
    book_id: str,
    session: AsyncSession = Depends(get_database_session),
) -> list[ArtifactSummary]:
    book = await session.get(Book, book_id)
    if book is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tracked book not found")

    result = await session.exec(
        select(Artifact).where(Artifact.book_id == book_id).order_by(Artifact.created_at.desc())
    )
    artifacts = result.all()
    return [
        ArtifactSummary(
            id=artifact.id,
            book_id=artifact.book_id,
            format=artifact.format,
            relative_path=artifact.relative_path,
            chapter_count=artifact.chapter_count,
            file_size_bytes=artifact.file_size_bytes,
            created_at=artifact.created_at,
        )
        for artifact in artifacts
    ]


@router.get("/{artifact_id}/download")
async def download_artifact(
    artifact_id: str,
    session: AsyncSession = Depends(get_database_session),
):
    artifact = await session.get(Artifact, artifact_id)
    if artifact is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Artifact not found")

    file_path = artifact_file_path(artifact.relative_path)
    if not file_path.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Artifact file not found")

    filename = file_path.name
    media_type = "application/json" if artifact.format == "manifest" else "application/octet-stream"
    return FileResponse(path=file_path, media_type=media_type, filename=filename)
