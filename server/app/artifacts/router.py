from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.builds.storage import artifact_file_path
from app.core.database import get_database_session
from app.models import Artifact, Book
from .service import (
    artifact_download_filename,
    artifact_media_type,
    build_download_headers,
    latest_artifact_for_book,
)
from .schemas import ArtifactSummary

router = APIRouter(prefix="/api/v1/artifacts", tags=["artifacts"])


def artifact_summary(artifact: Artifact) -> ArtifactSummary:
    return ArtifactSummary(
        id=artifact.id,
        book_id=artifact.book_id,
        format=artifact.format,
        relative_path=artifact.relative_path,
        chapter_count=artifact.chapter_count,
        file_size_bytes=artifact.file_size_bytes,
        created_at=artifact.created_at,
    )


def delete_artifact_file(relative_path: str) -> None:
    file_path = artifact_file_path(relative_path)
    if file_path.exists():
        file_path.unlink()


@router.get("", response_model=list[ArtifactSummary])
async def list_artifacts(
    session: AsyncSession = Depends(get_database_session),
) -> list[ArtifactSummary]:
    result = await session.exec(select(Artifact).order_by(Artifact.created_at.desc()))
    artifacts = result.all()
    return [artifact_summary(artifact) for artifact in artifacts]


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
    return [artifact_summary(artifact) for artifact in artifacts]


@router.get("/books/{book_id}/latest", response_model=ArtifactSummary | None)
async def get_latest_book_artifact(
    book_id: str,
    format: str | None = None,
    session: AsyncSession = Depends(get_database_session),
) -> ArtifactSummary | None:
    book = await session.get(Book, book_id)
    if book is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tracked book not found")

    artifact = await latest_artifact_for_book(session, book_id=book_id, format_name=format)
    if artifact is None:
        return None
    return artifact_summary(artifact)


@router.get("/{artifact_id}/download")
async def download_artifact(
    artifact_id: str,
    session: AsyncSession = Depends(get_database_session),
):
    artifact = await session.get(Artifact, artifact_id)
    if artifact is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Artifact not found")

    book = await session.get(Book, artifact.book_id)
    if book is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tracked book not found")

    file_path = artifact_file_path(artifact.relative_path)
    if not file_path.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Artifact file not found")

    return FileResponse(
        path=file_path,
        media_type=artifact_media_type(artifact),
        headers=build_download_headers(artifact_download_filename(book, artifact)),
    )


@router.delete("/{artifact_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_artifact(
    artifact_id: str,
    session: AsyncSession = Depends(get_database_session),
) -> None:
    artifact = await session.get(Artifact, artifact_id)
    if artifact is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Artifact not found")

    delete_artifact_file(artifact.relative_path)
    await session.delete(artifact)
    await session.commit()


@router.delete("/books/{book_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_book_artifacts(
    book_id: str,
    format: str | None = None,
    session: AsyncSession = Depends(get_database_session),
) -> None:
    book = await session.get(Book, book_id)
    if book is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tracked book not found")

    query = select(Artifact).where(Artifact.book_id == book_id)
    if format:
        query = query.where(Artifact.format == format)
    result = await session.exec(query)
    artifacts = result.all()

    for artifact in artifacts:
        delete_artifact_file(artifact.relative_path)
        await session.delete(artifact)
    await session.commit()
