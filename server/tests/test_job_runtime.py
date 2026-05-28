import json

from sqlmodel import select

from app.core.jobs import JobRuntime
from app.models import Artifact, Book, BookState, ChapterContentCache, ChapterSnapshot, JobEvent, JobRecord, TrackRule


class FakeRanobeLibClient:
    async def get_novel_info(self, slug: str):
        return {
            "id": 1,
            "rus_name": "Runtime Title",
            "authors": [{"name": "Runtime Author"}],
            "summary": "Runtime summary",
            "cover": {"default": "https://example.com/runtime.jpg"},
            "genres": [{"name": "Fantasy"}],
            "tags": [{"name": "Academy"}],
        }

    async def get_novel_chapters(self, slug: str):
        return [
            {
                "volume": "1",
                "number": "1",
                "name": "One",
                "index": 1,
                "branches": [{"branch_id": 7, "teams": [{"name": "Branch 7"}]}],
            },
            {
                "volume": "1",
                "number": "2",
                "name": "Two",
                "index": 2,
                "branches": [{"branch_id": 7, "teams": [{"name": "Branch 7"}]}],
            },
        ]

    async def get_chapter_content(self, slug: str, volume: str, number: str, branch_id: str | None = None):
        return {
            "content": f"<p>{slug}:{volume}:{number}:{branch_id or 'none'}</p>",
            "attachments": [],
        }

    async def close(self) -> None:
        return None


async def test_build_artifact_job_executes_and_persists_outputs(db, temp_data_dir, monkeypatch) -> None:
    async def fake_make_ranobelib_client(session):
        return FakeRanobeLibClient()

    monkeypatch.setattr("app.core.jobs.make_ranobelib_client", fake_make_ranobelib_client)

    book = Book(
        slug="test-slug",
        source_url="https://ranobelib.me/ru/book/test-slug",
        title="Test Title",
        author="Author",
        summary="Summary",
        available_chapters=2,
    )
    db.add(book)
    await db.commit()
    await db.refresh(book)

    db.add(
        TrackRule(
            book_id=book.id,
            branch_mode="default",
            selected_branch_id=None,
            selected_branch_label=None,
        )
    )
    db.add(
        BookState(
            book_id=book.id,
            last_remote_chapter_key="v1_ch2",
        )
    )
    db.add(
        ChapterSnapshot(
            book_id=book.id,
            chapter_key="v1_ch1",
            volume="1",
            number="1",
            title="One",
            branch_id="7",
            branch_name="Branch 7",
            ordinal_index=1,
        )
    )
    db.add(
        ChapterSnapshot(
            book_id=book.id,
            chapter_key="v1_ch2",
            volume="1",
            number="2",
            title="Two",
            branch_id="7",
            branch_name="Branch 7",
            ordinal_index=2,
        )
    )
    job = JobRecord(type="build_artifact", status="queued", book_id=book.id, payload_json=json.dumps({}))
    db.add(job)
    await db.commit()
    await db.refresh(job)

    runtime = JobRuntime()
    await runtime._run_single_job(db, job)

    await db.refresh(job)
    assert job.status == "completed"
    assert job.result_json is not None

    artifacts = (await db.exec(select(Artifact).where(Artifact.book_id == book.id))).all()
    assert len(artifacts) == 2
    assert {artifact.format for artifact in artifacts} == {"manifest", "epub"}

    caches = (await db.exec(select(ChapterContentCache).where(ChapterContentCache.book_id == book.id))).all()
    assert len(caches) == 2
    for cache in caches:
        assert (temp_data_dir / cache.relative_path).is_file()

    for artifact in artifacts:
        assert (temp_data_dir / artifact.relative_path).is_file()

    events = (await db.exec(select(JobEvent).where(JobEvent.job_id == job.id))).all()
    assert events
    assert any(event.event_type == "job.started" for event in events)
    assert any(event.event_type == "build.artifacts_written" for event in events)
    assert any(event.event_type == "job.completed" for event in events)


async def test_build_artifact_retention_keeps_latest_two_per_format(db, temp_data_dir, monkeypatch) -> None:
    async def fake_make_ranobelib_client(session):
        return FakeRanobeLibClient()

    monkeypatch.setattr("app.core.jobs.make_ranobelib_client", fake_make_ranobelib_client)

    book = Book(
        slug="retention-slug",
        source_url="https://ranobelib.me/ru/book/retention-slug",
        title="Retention Title",
        author="Author",
        summary="Summary",
        available_chapters=1,
    )
    db.add(book)
    await db.commit()
    await db.refresh(book)

    db.add(TrackRule(book_id=book.id, branch_mode="default"))
    db.add(BookState(book_id=book.id, last_remote_chapter_key="v1_ch1"))
    db.add(
        ChapterSnapshot(
            book_id=book.id,
            chapter_key="v1_ch1",
            volume="1",
            number="1",
            title="Only",
            branch_id="7",
            branch_name="Branch 7",
            ordinal_index=1,
        )
    )
    await db.commit()

    runtime = JobRuntime()
    seen_paths: set[str] = set()

    for _ in range(3):
        job = JobRecord(type="build_artifact", status="queued", book_id=book.id, payload_json=json.dumps({}))
        db.add(job)
        await db.commit()
        await db.refresh(job)
        await runtime._run_single_job(db, job)
        await db.refresh(job)
        artifacts = (await db.exec(select(Artifact).where(Artifact.book_id == book.id))).all()
        seen_paths.update(artifact.relative_path for artifact in artifacts)

    artifacts = (await db.exec(select(Artifact).where(Artifact.book_id == book.id))).all()
    assert len(artifacts) == 4
    counts: dict[str, int] = {}
    retained_paths = {artifact.relative_path for artifact in artifacts}
    for artifact in artifacts:
        counts[artifact.format] = counts.get(artifact.format, 0) + 1
        assert (temp_data_dir / artifact.relative_path).is_file()
    assert counts == {"manifest": 2, "epub": 2}
    pruned_paths = seen_paths - retained_paths
    assert pruned_paths
    for path in pruned_paths:
        assert not (temp_data_dir / path).exists()


async def test_check_updates_job_enqueues_build_when_artifact_is_stale(db, monkeypatch) -> None:
    async def fake_make_ranobelib_client(session):
        return FakeRanobeLibClient()

    monkeypatch.setattr("app.core.jobs.make_ranobelib_client", fake_make_ranobelib_client)

    book = Book(
        slug="check-book",
        source_url="https://ranobelib.me/ru/book/check-book",
        title="Check Book",
        available_chapters=2,
    )
    db.add(book)
    await db.commit()
    await db.refresh(book)

    db.add(TrackRule(book_id=book.id, branch_mode="default"))
    db.add(BookState(book_id=book.id, last_built_chapter_key="v1_ch1"))
    job = JobRecord(type="check_updates", status="queued", book_id=book.id, payload_json=json.dumps({}))
    db.add(job)
    await db.commit()
    await db.refresh(job)

    runtime = JobRuntime()
    await runtime._run_single_job(db, job)

    follow_up_jobs = (
        await db.exec(select(JobRecord).where(JobRecord.book_id == book.id, JobRecord.type == "build_artifact"))
    ).all()
    assert len(follow_up_jobs) == 1
    assert follow_up_jobs[0].status == "queued"
