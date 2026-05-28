import asyncio
import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.builds.service import build_book_artifact
from app.core.database import sessionmanager
from app.core.errors import TrackingError
from app.models import JobRecord
from app.jobs.service import log_job_event
from app.source_auth.service import make_ranobelib_client

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
    await session.flush()
    await log_job_event(
        session,
        job_id=record.id,
        level="info",
        event_type="job.queued",
        message=f"Queued {job_type} job",
        payload=payload or {},
    )
    await session.commit()
    await session.refresh(record)
    return EnqueueJobResult(job_id=record.id, status=record.status)


async def mark_job_started(session: AsyncSession, job: JobRecord) -> JobRecord:
    job.status = "running"
    job.started_at = utcnow()
    session.add(job)
    await log_job_event(
        session,
        job_id=job.id,
        level="info",
        event_type="job.started",
        message=f"Started {job.type} job",
    )
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
    await log_job_event(
        session,
        job_id=job.id,
        level="error" if status == "failed" else "info",
        event_type=f"job.{status}",
        message=f"Job {status}",
        payload=result if status != "failed" else {"error_message": error_message},
    )
    await session.commit()
    await session.refresh(job)
    return job


class JobRuntime:
    """Minimal runtime stub. The backend owns persisted jobs from day one."""

    def __init__(self) -> None:
        self._heartbeat_task: asyncio.Task | None = None
        self._tick_interval_seconds = 5

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
            await self.run_pending_jobs()
            await asyncio.sleep(self._tick_interval_seconds)

    async def pending_jobs(self, session: AsyncSession) -> list[JobRecord]:
        result = await session.exec(select(JobRecord).where(JobRecord.status == "queued"))
        return list(result)

    async def run_pending_jobs(self) -> None:
        async with sessionmanager.session() as session:
            jobs = await self.pending_jobs(session)
            for job in jobs:
                await self._run_single_job(session, job)

    async def _run_single_job(self, session: AsyncSession, job: JobRecord) -> None:
        from app.tracking.service import process_check_updates_job

        await mark_job_started(session, job)
        client = await make_ranobelib_client(session)
        try:
            await log_job_event(
                session,
                job_id=job.id,
                level="info",
                event_type="job.client_ready",
                message="Prepared RanobeLib client",
            )
            if job.type == "check_updates":
                await log_job_event(
                    session,
                    job_id=job.id,
                    level="info",
                    event_type="job.check_updates",
                    message="Checking remote chapter updates",
                )
                result = await process_check_updates_job(
                    session,
                    client,
                    job,
                    event_logger=lambda **kwargs: log_job_event(session, job_id=job.id, **kwargs),
                )
            elif job.type == "build_artifact":
                if not job.book_id:
                    raise TrackingError("Build job is missing a book_id")
                payload = json.loads(job.payload_json or "{}")
                await log_job_event(
                    session,
                    job_id=job.id,
                    level="info",
                    event_type="job.build_artifact",
                    message="Building artifacts from cached chapters",
                )
                result = await build_book_artifact(
                    session,
                    client,
                    book_id=job.book_id,
                    requested_formats=payload.get("formats"),
                    event_logger=lambda **kwargs: log_job_event(session, job_id=job.id, **kwargs),
                )
            else:
                raise TrackingError(f"Unsupported job type: {job.type}")
            await mark_job_finished(session, job, status="completed", result=result)
        except Exception as exc:
            logger.exception("Job execution failed", extra={"job_id": job.id, "job_type": job.type})
            await mark_job_finished(session, job, status="failed", error_message=str(exc))
        finally:
            await client.close()


job_runtime = JobRuntime()
