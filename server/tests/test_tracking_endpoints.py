from sqlmodel import select

from app.core.titles import normalize_book_title
from app.models import (
    Artifact,
    Book,
    BookState,
    ChapterContentCache,
    ChapterSnapshot,
    CollectionBook,
    JobEvent,
    JobRecord,
    TrackRule,
    UserCollection,
)
from app.tracking.service import (
    branch_id_of,
    chapter_key,
    normalize_summary_value,
    resolve_author_label,
    select_chapters_for_rule,
)


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


def test_normalize_summary_value_from_doc_payload() -> None:
    summary = {
        "type": "doc",
        "content": [
            {
                "type": "paragraph",
                "content": [
                    {"type": "text", "text": "First line"},
                    {"type": "hardBreak"},
                    {"type": "text", "text": "second line"},
                ],
            },
            {
                "type": "paragraph",
                "content": [{"type": "text", "text": "Next block"}],
            },
        ],
    }

    normalized = normalize_summary_value(summary)
    assert normalized == "First line second line Next block"


def test_normalize_book_title_strips_novella_suffix() -> None:
    assert normalize_book_title("Title (Новелла)") == "Title"
    assert normalize_book_title("Title   (новелла)   ") == "Title"


def test_resolve_author_label_falls_back_to_publisher() -> None:
    assert resolve_author_label({"authors": [{"name": "Author"}], "publisher": {"name": "Publisher"}}) == "Author"
    assert resolve_author_label({"publisher": {"name": "Publisher"}}) == "Publisher"


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


async def test_source_auth_validate_without_credentials(client) -> None:
    response = await client.post("/api/v1/source-auth/ranobelib/validate")
    assert response.status_code == 200
    payload = response.json()
    assert payload["valid"] is False
    assert payload["authenticated"] is False
    assert payload["error"] == "No stored access token"


async def test_source_auth_validate_with_remote_user(client, db, monkeypatch) -> None:
    class FakeRanobeLibClient:
        async def get_current_user(self):
            return {"id": 42, "username": "reader", "email": "reader@example.com"}

        async def close(self) -> None:
            return None

    async def fake_make_ranobelib_client(session):
        return FakeRanobeLibClient()

    monkeypatch.setattr("app.source_auth.service.make_ranobelib_client", fake_make_ranobelib_client)

    response = await client.put(
        "/api/v1/source-auth/ranobelib",
        json={"access_token": "token-a", "refresh_token": "token-r"},
    )
    assert response.status_code == 200

    response = await client.post("/api/v1/source-auth/ranobelib/validate")
    assert response.status_code == 200
    payload = response.json()
    assert payload["valid"] is True
    assert payload["authenticated"] is True
    assert payload["user_id"] == "42"
    assert payload["username"] == "reader"
    assert payload["email"] == "reader@example.com"


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


async def test_preview_endpoint_returns_branches_and_metadata(client, monkeypatch) -> None:
    class FakeRanobeLibClient:
        @staticmethod
        def extract_slug_from_url(url: str) -> str | None:
            return "preview-book"

        async def get_novel_info(self, slug: str):
            assert slug == "preview-book"
            return {
                "id": 1,
                "rus_name": "Preview Book",
                "authors": [{"name": "Preview Author"}],
                "summary": "Preview summary",
                "cover": {"default": "https://example.com/cover.jpg"},
                "genres": [{"name": "Fantasy"}],
                "tags": [{"name": "Academy"}],
            }

        async def get_novel_chapters(self, slug: str):
            return [
                {
                    "volume": "1",
                    "number": "1",
                    "name": "Chapter 1",
                    "index": 1,
                    "branches": [{"branch_id": 5, "teams": [{"name": "Main Team"}]}],
                }
            ]

        async def close(self) -> None:
            return None

    async def fake_make_ranobelib_client(_session):
        return FakeRanobeLibClient()

    monkeypatch.setattr("app.tracking.router.make_ranobelib_client", fake_make_ranobelib_client)

    response = await client.post("/api/v1/tracking/preview", json={"url": "https://ranobelib.me/ru/book/preview-book"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["title"] == "Preview Book"
    assert payload["author"] == "Preview Author"
    assert payload["branches"][0]["id"] == "5"
    assert payload["genres"][0]["name"] == "Fantasy"
    assert payload["tags"][0]["name"] == "Academy"


async def test_branch_update_endpoint_enqueues_refresh(client, db) -> None:
    book = Book(
        slug="branch-book",
        source_url="https://ranobelib.me/ru/book/branch-book",
        title="Branch Book",
        branches_json='[{"id":"5","name":"Main","chapter_count":10,"team_names":["Main Team"],"display":"Main Team"}]',
        available_chapters=10,
    )
    db.add(book)
    await db.commit()
    await db.refresh(book)

    from app.models import TrackRule, BookState

    db.add(TrackRule(book_id=book.id, branch_mode="default"))
    db.add(BookState(book_id=book.id, last_remote_chapter_key="v1_ch10"))
    await db.commit()

    response = await client.patch(
        f"/api/v1/tracking/books/{book.id}/branch",
        json={"selected_branch_id": "5"},
    )
    assert response.status_code == 202

    rule = (await db.exec(select(TrackRule).where(TrackRule.book_id == book.id))).one()
    assert rule.branch_mode == "selected"
    assert rule.selected_branch_id == "5"

    queued_job = (
        await db.exec(
            select(JobRecord).where(JobRecord.book_id == book.id, JobRecord.type == "check_updates")
        )
    ).one()
    assert '"selected_branch_id": "5"' in queued_job.payload_json


async def test_delete_tracked_book_removes_related_rows_and_files(client, db, temp_data_dir) -> None:
    book = Book(
        slug="delete-book",
        source_url="https://ranobelib.me/ru/book/delete-book",
        title="Delete Book",
        author="Delete Author",
    )
    db.add(book)
    await db.commit()
    await db.refresh(book)

    artifact_path = temp_data_dir / "artifacts" / book.id / "book.epub"
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    artifact_path.write_bytes(b"epub")
    cache_path = temp_data_dir / "cache" / "chapters" / book.id / "v1_ch1.json"
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text("{}", encoding="utf-8")

    db.add(TrackRule(book_id=book.id))
    db.add(BookState(book_id=book.id, last_remote_chapter_key="v1_ch1"))
    db.add(ChapterSnapshot(book_id=book.id, chapter_key="v1_ch1", volume="1", number="1"))
    db.add(
        ChapterContentCache(
            book_id=book.id,
            chapter_key="v1_ch1",
            content_type="html",
            relative_path=str(cache_path.relative_to(temp_data_dir)),
            content_hash="hash",
        )
    )
    db.add(
        Artifact(
            book_id=book.id,
            format="epub",
            relative_path=str(artifact_path.relative_to(temp_data_dir)),
            chapter_count=1,
            file_size_bytes=4,
        )
    )
    collection = UserCollection(slug="cleanup", name="Cleanup")
    db.add(collection)
    job = JobRecord(type="check_updates", status="completed", book_id=book.id)
    db.add(job)
    await db.commit()
    await db.refresh(collection)
    db.add(CollectionBook(collection_id=collection.id, book_id=book.id))
    await db.refresh(job)
    db.add(JobEvent(job_id=job.id, level="info", event_type="job.completed", message="done"))
    await db.commit()

    response = await client.delete(f"/api/v1/tracking/books/{book.id}")
    assert response.status_code == 204

    assert await db.get(Book, book.id) is None
    assert (await db.exec(select(TrackRule).where(TrackRule.book_id == book.id))).first() is None
    assert (await db.exec(select(BookState).where(BookState.book_id == book.id))).first() is None
    assert (await db.exec(select(ChapterSnapshot).where(ChapterSnapshot.book_id == book.id))).first() is None
    assert (await db.exec(select(ChapterContentCache).where(ChapterContentCache.book_id == book.id))).first() is None
    assert (await db.exec(select(Artifact).where(Artifact.book_id == book.id))).first() is None
    assert (await db.exec(select(JobRecord).where(JobRecord.book_id == book.id))).first() is None
    assert (await db.exec(select(JobEvent).where(JobEvent.job_id == job.id))).first() is None
    assert (await db.exec(select(CollectionBook).where(CollectionBook.book_id == book.id))).first() is None
    assert not artifact_path.exists()
    assert not cache_path.exists()


async def test_tracked_books_support_updated_sort(client, db) -> None:
    first = Book(
        slug="first-sort-book",
        source_url="https://ranobelib.me/ru/book/first-sort-book",
        title="First Sort Book",
        available_chapters=1,
    )
    second = Book(
        slug="second-sort-book",
        source_url="https://ranobelib.me/ru/book/second-sort-book",
        title="Second Sort Book",
        available_chapters=1,
    )
    db.add(first)
    db.add(second)
    await db.commit()
    await db.refresh(first)
    await db.refresh(second)

    db.add(TrackRule(book_id=first.id))
    db.add(TrackRule(book_id=second.id))
    db.add(BookState(book_id=first.id, last_remote_chapter_key="v1_ch1"))
    db.add(BookState(book_id=second.id, last_remote_chapter_key="v1_ch1"))
    await db.commit()

    second.title = "A Second Sort Book"
    await db.commit()

    response = await client.get("/api/v1/tracking/books?sort=title")
    assert response.status_code == 200
    payload = response.json()
    assert payload[0]["title"] == "A Second Sort Book"


async def test_book_preferences_update_can_set_current_rating_comment_and_visible_metadata(client, db) -> None:
    book = Book(
        slug="prefs-book",
        source_url="https://ranobelib.me/ru/book/prefs-book",
        title="Prefs Book",
        genres_json='[{"name":"Fantasy","slug":"fantasy"},{"name":"Drama","slug":"drama"}]',
        tags_json='[{"name":"Academy","slug":"academy"},{"name":"Magic","slug":"magic"}]',
        available_chapters=2,
    )
    other_current = Book(
        slug="other-current-book",
        source_url="https://ranobelib.me/ru/book/other-current-book",
        title="Other Current",
        is_current=True,
        available_chapters=1,
    )
    collection = UserCollection(slug="favorites", name="Favorites")
    db.add(book)
    db.add(other_current)
    db.add(collection)
    await db.commit()
    await db.refresh(book)
    await db.refresh(other_current)
    await db.refresh(collection)

    db.add(TrackRule(book_id=book.id))
    db.add(TrackRule(book_id=other_current.id))
    db.add(BookState(book_id=book.id, last_remote_chapter_key="v1_ch2"))
    db.add(BookState(book_id=other_current.id, last_remote_chapter_key="v1_ch1"))
    await db.commit()

    response = await client.patch(
        f"/api/v1/tracking/books/{book.id}/preferences",
        json={
            "opds_visible_genre_slugs": ["fantasy"],
            "opds_visible_tag_slugs": ["academy"],
            "is_favorite": True,
            "is_current": True,
            "rating": 5,
            "comment": "strong title",
            "collection_ids": [collection.id],
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert [item["slug"] for item in payload["opds_visible_genres"]] == ["fantasy"]
    assert [item["slug"] for item in payload["opds_visible_tags"]] == ["academy"]
    assert payload["is_favorite"] is True
    assert payload["is_current"] is True
    assert payload["rating"] == 5
    assert payload["comment"] == "strong title"
    assert payload["collections"][0]["id"] == collection.id

    await db.refresh(other_current)
    assert other_current.is_current is False
    membership = (await db.exec(select(CollectionBook).where(CollectionBook.book_id == book.id))).all()
    assert len(membership) == 1


async def test_library_collection_crud(client) -> None:
    response = await client.post(
        "/api/v1/library/collections",
        json={"name": "Weekend Reads", "description": "Fast picks", "sort_order": 3},
    )
    assert response.status_code == 201
    collection = response.json()
    assert collection["name"] == "Weekend Reads"
    assert collection["book_count"] == 0

    response = await client.get("/api/v1/library/collections")
    assert response.status_code == 200
    assert response.json()[0]["name"] == "Weekend Reads"

    response = await client.patch(
        f"/api/v1/library/collections/{collection['id']}",
        json={"description": "Updated", "sort_order": 1},
    )
    assert response.status_code == 200
    assert response.json()["description"] == "Updated"

    response = await client.delete(f"/api/v1/library/collections/{collection['id']}")
    assert response.status_code == 204
