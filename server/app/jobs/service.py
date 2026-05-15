import json

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models import JobEvent


async def log_job_event(
    session: AsyncSession,
    *,
    job_id: str,
    level: str,
    event_type: str,
    message: str,
    payload: dict | None = None,
) -> JobEvent:
    event = JobEvent(
        job_id=job_id,
        level=level,
        event_type=event_type,
        message=message,
        payload_json=json.dumps(payload, ensure_ascii=False) if payload is not None else None,
    )
    session.add(event)
    await session.flush()
    return event


async def list_job_events(session: AsyncSession, *, job_id: str) -> list[JobEvent]:
    result = await session.exec(
        select(JobEvent).where(JobEvent.job_id == job_id).order_by(JobEvent.created_at.asc(), JobEvent.id.asc())
    )
    return result.all()
