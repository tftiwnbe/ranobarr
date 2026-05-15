import json

from sqlmodel import select

from app.core.jobs import JobRuntime
from app.models import Artifact, Book, BookState, ChapterContentCache, ChapterSnapshot, JobRecord, TrackRule


class FakeRanobeLibClient:
    async def get_chapter_content(self, slug: str, volume: str, number: str, branch_id: str | None = None):
        return {
            "content": f"<p>{slug}:{volume}:{number}:{branch_id or 'none'}</p>",
            "attachments": [],
        }

    async def close(self) -> None:
        return None


async def test_build_artifact_job_executes_and_persists_outputs(db, temp_data_dir, monkeypatch) -> None:
    monkeypatch.setattr("app.core.jobs.RanobeLibClient", FakeRanobeLibClient)

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
