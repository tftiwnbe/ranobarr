import json

from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.database import get_database_session
from app.core.titles import normalize_book_title
from app.models import Book, JobRecord
from .schemas import JobDetail, JobEventView, JobSummary
from .service import list_job_events

router = APIRouter(prefix="/api/v1/jobs", tags=["jobs"])


@router.get("", response_model=list[JobSummary])
async def list_jobs(
    session: AsyncSession = Depends(get_database_session),
) -> list[JobSummary]:
    result = await session.exec(select(JobRecord).order_by(JobRecord.created_at.desc()))
    jobs = result.all()
    book_ids = [job.book_id for job in jobs if job.book_id]
    books_by_id: dict[str, Book] = {}
    if book_ids:
        book_result = await session.exec(select(Book).where(Book.id.in_(book_ids)))
        books_by_id = {book.id: book for book in book_result.all()}
    return [
        JobSummary(
            id=job.id,
            type=job.type,
            status=job.status,
            book_id=job.book_id,
            book_title=normalize_book_title(books_by_id[job.book_id].title) if job.book_id and job.book_id in books_by_id else None,
            trigger=_job_trigger(job),
            error_message=job.error_message,
            created_at=job.created_at,
            started_at=job.started_at,
            finished_at=job.finished_at,
        )
        for job in jobs
    ]


@router.get("/{job_id}", response_model=JobDetail)
async def get_job(
    job_id: str,
    session: AsyncSession = Depends(get_database_session),
) -> JobDetail:
    job = await session.get(JobRecord, job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    book = await session.get(Book, job.book_id) if job.book_id else None

    return JobDetail(
        id=job.id,
        type=job.type,
        status=job.status,
        book_id=job.book_id,
        book_title=normalize_book_title(book.title) if book is not None else None,
        trigger=_job_trigger(job),
        error_message=job.error_message,
        created_at=job.created_at,
        started_at=job.started_at,
        finished_at=job.finished_at,
        payload_json=job.payload_json,
        result_json=job.result_json,
    )


@router.get("/{job_id}/events", response_model=list[JobEventView])
async def get_job_events(
    job_id: str,
    session: AsyncSession = Depends(get_database_session),
) -> list[JobEventView]:
    job = await session.get(JobRecord, job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")

    events = await list_job_events(session, job_id=job_id)
    return [
        JobEventView(
            id=event.id,
            job_id=event.job_id,
            level=event.level,
            event_type=event.event_type,
            message=event.message,
            payload_json=event.payload_json,
            created_at=event.created_at,
        )
        for event in events
    ]


def _job_trigger(job: JobRecord) -> str | None:
    try:
        payload = json.loads(job.payload_json or "{}")
    except json.JSONDecodeError:
        return None
    trigger = payload.get("trigger")
    return str(trigger) if trigger else None
