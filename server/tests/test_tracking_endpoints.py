from sqlmodel import select

from app.models import Artifact, Book, JobEvent, JobRecord
from app.tracking.service import branch_id_of, chapter_key, select_chapters_for_rule


def test_chapter_key() -> None:
    assert chapter_key(1, 2) == "v1_ch2"
    assert chapter_key(None, None) == "v1_ch0"


def test_select_chapters_for_rule_default_branch() -> None:
    chapters = [
        {
            "volume": "1",
            "number": "1",
            "name": "Chapter 1",
            "index": 1,
            "branches": [{"branch_id": 5, "teams": [{"name": "A"}]}],
        },
        {
            "volume": "1",
            "number": "2",
            "name": "Chapter 2",
            "index": 2,
            "branches": [{"branch_id": 5, "teams": [{"name": "A"}]}],
        },
    ]
    selected = select_chapters_for_rule(chapters, branch_mode="default", selected_branch_id=None)
    assert [item.chapter_key for item in selected] == ["v1_ch1", "v1_ch2"]
    assert selected[0].branch_id == "5"


def test_branch_id_of() -> None:
    assert branch_id_of({"branch_id": 9}) == "9"
    assert branch_id_of(None) is None


async def test_healthcheck(client) -> None:
    response = await client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_jobs_endpoint_empty(client) -> None:
    response = await client.get("/api/v1/jobs")
    assert response.status_code == 200
    assert response.json() == []


async def test_artifacts_endpoint_empty(client) -> None:
    response = await client.get("/api/v1/artifacts")
    assert response.status_code == 200
    assert response.json() == []


async def test_source_auth_crud(client) -> None:
    response = await client.get("/api/v1/source-auth/ranobelib")
    assert response.status_code == 200
    assert response.json() is None

    response = await client.put(
        "/api/v1/source-auth/ranobelib",
        json={"access_token": "token-a", "refresh_token": "token-r"},
    )
    assert response.status_code == 200
    assert response.json()["has_access_token"] is True
    assert response.json()["has_refresh_token"] is True

    response = await client.delete("/api/v1/source-auth/ranobelib")
    assert response.status_code == 204


async def test_latest_artifact_endpoint_empty_for_unknown_book(client) -> None:
    response = await client.get("/api/v1/artifacts/books/missing/latest")
    assert response.status_code == 404


async def test_latest_artifact_endpoint_returns_newest_match(client, db) -> None:
    book = Book(
        slug="artifact-book",
        source_url="https://ranobelib.me/ru/book/artifact-book",
        title="Artifact Book",
        available_chapters=1,
    )
    db.add(book)
    await db.commit()
    await db.refresh(book)

    older = Artifact(
        book_id=book.id,
        format="epub",
        relative_path="artifacts/old.epub",
        chapter_count=1,
        file_size_bytes=100,
    )
    newer = Artifact(
        book_id=book.id,
        format="epub",
        relative_path="artifacts/new.epub",
        chapter_count=2,
        file_size_bytes=200,
    )
    manifest = Artifact(
        book_id=book.id,
        format="manifest",
        relative_path="artifacts/new.json",
        chapter_count=2,
        file_size_bytes=80,
    )
    db.add(older)
    await db.commit()
    db.add(newer)
    db.add(manifest)
    await db.commit()

    response = await client.get(f"/api/v1/artifacts/books/{book.id}/latest?format=epub")
    assert response.status_code == 200
    assert response.json()["relative_path"] == "artifacts/new.epub"


async def test_delete_artifact_endpoint_removes_row_and_file(client, db, temp_data_dir) -> None:
    book = Book(
        slug="delete-artifact-book",
        source_url="https://ranobelib.me/ru/book/delete-artifact-book",
        title="Delete Artifact Book",
        available_chapters=1,
    )
    db.add(book)
    await db.commit()
    await db.refresh(book)

    artifact_path = temp_data_dir / "artifacts" / "delete-artifact-book" / "book.epub"
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    artifact_path.write_bytes(b"epub-bytes")

    artifact = Artifact(
        book_id=book.id,
        format="epub",
        relative_path=str(artifact_path.relative_to(temp_data_dir)),
        chapter_count=1,
        file_size_bytes=artifact_path.stat().st_size,
    )
    db.add(artifact)
    await db.commit()

    response = await client.delete(f"/api/v1/artifacts/{artifact.id}")
    assert response.status_code == 204
    assert artifact_path.exists() is False
    assert await db.get(Artifact, artifact.id) is None


async def test_delete_book_artifacts_endpoint_filters_by_format(client, db, temp_data_dir) -> None:
    book = Book(
        slug="delete-book-artifacts",
        source_url="https://ranobelib.me/ru/book/delete-book-artifacts",
        title="Delete Book Artifacts",
        available_chapters=2,
    )
    db.add(book)
    await db.commit()
    await db.refresh(book)

    epub_path = temp_data_dir / "artifacts" / book.id / "book.epub"
    manifest_path = temp_data_dir / "artifacts" / book.id / "manifest.json"
    epub_path.parent.mkdir(parents=True, exist_ok=True)
    epub_path.write_bytes(b"epub")
    manifest_path.write_text("{}", encoding="utf-8")

    epub_artifact = Artifact(
        book_id=book.id,
        format="epub",
        relative_path=str(epub_path.relative_to(temp_data_dir)),
        chapter_count=2,
        file_size_bytes=epub_path.stat().st_size,
    )
    manifest_artifact = Artifact(
        book_id=book.id,
        format="manifest",
        relative_path=str(manifest_path.relative_to(temp_data_dir)),
        chapter_count=2,
        file_size_bytes=manifest_path.stat().st_size,
    )
    db.add(epub_artifact)
    db.add(manifest_artifact)
    await db.commit()

    response = await client.delete(f"/api/v1/artifacts/books/{book.id}?format=epub")
    assert response.status_code == 204
    assert epub_path.exists() is False
    assert manifest_path.exists() is True
    assert await db.get(Artifact, epub_artifact.id) is None
    assert await db.get(Artifact, manifest_artifact.id) is not None


async def test_job_events_endpoint_returns_events(client, db) -> None:
    job = JobRecord(type="check_updates", status="completed", payload_json="{}")
    db.add(job)
    await db.commit()
    await db.refresh(job)

    db.add(
        JobEvent(
            job_id=job.id,
            level="info",
            event_type="job.completed",
            message="Job completed",
            payload_json='{"ok":true}',
        )
    )
    await db.commit()

    response = await client.get(f"/api/v1/jobs/{job.id}/events")
    assert response.status_code == 200
    payload = response.json()
    assert len(payload) == 1
    assert payload[0]["event_type"] == "job.completed"


async def test_build_endpoint_enqueues_requested_formats(client, db) -> None:
    book = Book(
        slug="build-book",
        source_url="https://ranobelib.me/ru/book/build-book",
        title="Build Book",
        available_chapters=1,
    )
    db.add(book)
    await db.commit()
    await db.refresh(book)

    from app.models import TrackRule

    db.add(
        TrackRule(
            book_id=book.id,
            branch_mode="default",
            selected_branch_id=None,
        )
    )
    from app.models import BookState

    db.add(BookState(book_id=book.id, last_remote_chapter_key="v1_ch1"))
    await db.commit()

    response = await client.post(
        f"/api/v1/tracking/books/{book.id}/build",
        json={"formats": ["manifest"]},
    )
    assert response.status_code == 202

    result = await db.exec(
        select(JobRecord).where(JobRecord.book_id == book.id, JobRecord.type == "build_artifact")
    )
    job = result.one()
    assert '"formats": ["manifest"]' in job.payload_json
