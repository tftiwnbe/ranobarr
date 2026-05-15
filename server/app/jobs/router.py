from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.database import get_database_session
from app.models import JobRecord
from .schemas import JobDetail, JobEventView, JobSummary
from .service import list_job_events

router = APIRouter(prefix="/api/v1/jobs", tags=["jobs"])


@router.get("", response_model=list[JobSummary])
async def list_jobs(
    session: AsyncSession = Depends(get_database_session),
) -> list[JobSummary]:
    result = await session.exec(select(JobRecord).order_by(JobRecord.created_at.desc()))
    jobs = result.all()
    return [
        JobSummary(
            id=job.id,
            type=job.type,
            status=job.status,
            book_id=job.book_id,
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

    return JobDetail(
        id=job.id,
        type=job.type,
        status=job.status,
        book_id=job.book_id,
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
