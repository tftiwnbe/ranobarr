import asyncio
import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models import JobRecord

logger = logging.getLogger(__name__)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(slots=True)
class EnqueueJobResult:
    job_id: str
    status: str


async def enqueue_job(
    session: AsyncSession,
    *,
    job_type: str,
    status: str = "queued",
    book_id: str | None = None,
    payload: dict | None = None,
) -> EnqueueJobResult:
    record = JobRecord(
        type=job_type,
        status=status,
        book_id=book_id,
        payload_json=json.dumps(payload or {}, ensure_ascii=False),
    )
    session.add(record)
    await session.commit()
    await session.refresh(record)
    return EnqueueJobResult(job_id=record.id, status=record.status)


async def mark_job_started(session: AsyncSession, job: JobRecord) -> JobRecord:
    job.status = "running"
    job.started_at = utcnow()
    session.add(job)
    await session.commit()
    await session.refresh(job)
    return job


async def mark_job_finished(
    session: AsyncSession,
    job: JobRecord,
    *,
    status: str,
    result: dict | None = None,
    error_message: str | None = None,
) -> JobRecord:
    job.status = status
    job.finished_at = utcnow()
    job.result_json = json.dumps(result or {}, ensure_ascii=False) if result is not None else None
    job.error_message = error_message
    session.add(job)
    await session.commit()
    await session.refresh(job)
    return job


class JobRuntime:
    """Minimal runtime stub. The backend owns persisted jobs from day one."""

    def __init__(self) -> None:
        self._heartbeat_task: asyncio.Task | None = None

    async def start(self) -> None:
        if self._heartbeat_task is None:
            self._heartbeat_task = asyncio.create_task(self._heartbeat(), name="job-runtime-heartbeat")

    async def stop(self) -> None:
        if self._heartbeat_task is None:
            return
        self._heartbeat_task.cancel()
        try:
            await self._heartbeat_task
        except asyncio.CancelledError:
            pass
        self._heartbeat_task = None

    async def _heartbeat(self) -> None:
        while True:
            logger.debug("Job runtime heartbeat")
            await asyncio.sleep(60)

    async def pending_jobs(self, session: AsyncSession) -> list[JobRecord]:
        result = await session.exec(select(JobRecord).where(JobRecord.status == "queued"))
        return list(result)


job_runtime = JobRuntime()
