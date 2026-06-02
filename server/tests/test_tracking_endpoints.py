import hashlib
import tempfile

from ebooklib import epub
from sqlmodel import select

from app.core.titles import normalize_book_title
from app.models import (
    Artifact,
    BinaryAssetCache,
    Book,
    BookState,
    ChapterContentCache,
    ChapterSnapshot,
    CollectionBook,
    JobEvent,
    JobRecord,
    KOReaderSyncDocument,
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


def build_test_epub_bytes(title: str, author: str, *, cover_bytes: bytes | None = None) -> bytes:
    book = epub.EpubBook()
    book.set_identifier(f"test-{title}")
    book.set_title(title)
    book.add_author(author)
    if cover_bytes is not None:
        book.set_cover("cover.jpg", cover_bytes, create_page=False)
    chapter = epub.EpubHtml(title="Chapter 1", file_name="chapter-1.xhtml")
    chapter.set_content(f"<h1>{title}</h1><p>Test chapter</p>")
    book.add_item(chapter)
    book.toc = [chapter]
    book.spine = ["nav", chapter]
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())

    with tempfile.NamedTemporaryFile(suffix=".epub") as temp_file:
        epub.write_epub(temp_file.name, book, {})
        temp_file.seek(0)
        return temp_file.read()


def build_test_epub_bytes_with_cover_page(title: str, author: str, *, cover_bytes: bytes) -> bytes:
    book = epub.EpubBook()
    book.set_identifier(f"test-cover-page-{title}")
    book.set_title(title)
    book.add_author(author)

    cover_image = epub.EpubItem(
        uid="x01.jpg",
        file_name="Images/01.jpg",
        media_type="image/jpeg",
        content=cover_bytes,
    )
    cover_page = epub.EpubHtml(title="Cover", file_name="Text/cover.xhtml")
    cover_page.set_content(
        """
        <html xmlns="http://www.w3.org/1999/xhtml">
          <body>
            <svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink">
              <image xlink:href="../Images/01.jpg" />
            </svg>
          </body>
        </html>
        """
    )
    chapter = epub.EpubHtml(title="Chapter 1", file_name="Text/chapter-1.xhtml")
    chapter.set_content(f"<h1>{title}</h1><p>Test chapter</p>")

    book.add_item(cover_image)
    book.add_item(cover_page)
    book.add_item(chapter)
    book.add_metadata("OPF", "meta", "", {"name": "cover", "content": "x01.jpg"})
    book.toc = [chapter]
    book.spine = [cover_page, "nav", chapter]
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())

    with tempfile.NamedTemporaryFile(suffix=".epub") as temp_file:
        epub.write_epub(temp_file.name, book, {})
        temp_file.seek(0)
        return temp_file.read()


async def test_healthcheck(client) -> None:
    response = await client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_jobs_endpoint_empty(client) -> None:
    response = await client.get("/api/v1/jobs")
    assert response.status_code == 200
    assert response.json() == []


async def test_jobs_endpoint_includes_title_and_trigger(client, db) -> None:
    book = Book(
        slug="job-book",
        source_url="https://ranobelib.me/ru/book/job-book",
        title="Job Book",
    )
    db.add(book)
    await db.commit()
    await db.refresh(book)
    db.add(JobRecord(type="build_artifact", status="queued", book_id=book.id, payload_json='{"trigger":"manual"}'))
    await db.commit()

    response = await client.get("/api/v1/jobs")
    assert response.status_code == 200
    payload = response.json()
    assert payload[0]["book_title"] == "Job Book"
    assert payload[0]["trigger"] == "manual"


async def test_tracked_books_expose_chapter_added_timestamp_as_utc(client, db) -> None:
    book = Book(
        slug="chapter-added-book",
        source_url="https://ranobelib.me/ru/book/chapter-added-book",
        title="Chapter Added Book",
    )
    db.add(book)
    await db.commit()
    await db.refresh(book)

    db.add(TrackRule(book_id=book.id))
    state = BookState(
        book_id=book.id,
        last_remote_chapter_key="v1_ch9",
    )
    state.last_chapter_added_at = state.created_at.replace(hour=5, minute=0, second=0, microsecond=0, tzinfo=None)
    db.add(state)
    await db.commit()

    response = await client.get("/api/v1/tracking/books?sort=updated")
    assert response.status_code == 200
    payload = response.json()
    assert payload[0]["last_chapter_added_at"].endswith("Z")
    assert payload[0]["last_chapter_added_at"].startswith(str(state.last_chapter_added_at.date()))


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


async def test_koreader_protocol_sync_links_matching_artifact(client, db, temp_data_dir) -> None:
    tracked = Book(
        slug="example-title",
        source_url="https://ranobelib.me/ru/book/example-title",
        title="Example Title",
    )
    db.add(tracked)
    await db.commit()
    await db.refresh(tracked)

    artifact_bytes = b"example-epub-binary"
    artifact_hash = hashlib.md5(artifact_bytes).hexdigest()
    artifact_path = temp_data_dir / "artifacts" / tracked.id / "book.epub"
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    artifact_path.write_bytes(artifact_bytes)
    db.add(
        Artifact(
            book_id=tracked.id,
            format="epub",
            relative_path=str(artifact_path.relative_to(temp_data_dir)),
            chapter_count=12,
            file_size_bytes=len(artifact_bytes),
        )
    )
    await db.commit()

    response = await client.post("/users/create", json={"username": "reader1", "password": "md5pass"})
    assert response.status_code == 201
    assert response.json() == {"username": "reader1"}

    response = await client.get("/users/auth", headers={"x-auth-user": "reader1", "x-auth-key": "md5pass"})
    assert response.status_code == 200
    assert response.json() == {"authorized": "OK"}

    response = await client.put(
        "/syncs/progress",
        headers={"x-auth-user": "reader1", "x-auth-key": "md5pass"},
        json={
            "document": artifact_hash,
            "progress": "chapter-29",
            "percentage": 0.42,
            "device": "xteink x4",
            "device_id": "device-1",
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["document"] == artifact_hash
    assert payload["timestamp"] > 0

    response = await client.get(
        f"/syncs/progress/{artifact_hash}",
        headers={"x-auth-user": "reader1", "x-auth-key": "md5pass"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["document"] == artifact_hash
    assert payload["percentage"] == 0.42
    assert payload["progress"] == "chapter-29"
    assert payload["device"] == "xteink x4"
    assert payload["device_id"] == "device-1"

    response = await client.get("/api/v1/koreader")
    assert response.status_code == 200
    payload = response.json()
    assert len(payload["documents"]) == 1
    assert payload["documents"][0]["linked_book_id"] == tracked.id
    assert payload["documents"][0]["linked_book_title"] == "Example Title"


async def test_koreader_protocol_sync_links_matching_filename_hash(client, db) -> None:
    tracked = Book(
        slug="filename-title",
        source_url="https://ranobelib.me/ru/book/filename-title",
        title="Filename Title",
        author="Filename Author",
    )
    db.add(tracked)
    await db.commit()
    await db.refresh(tracked)

    filename_hash = hashlib.md5("Filename Author - Filename Title.epub".encode("utf-8")).hexdigest()

    response = await client.post("/users/create", json={"username": "reader-filename", "password": "md5pass"})
    assert response.status_code == 201

    response = await client.put(
        "/syncs/progress",
        headers={"x-auth-user": "reader-filename", "x-auth-key": "md5pass"},
        json={
            "document": filename_hash,
            "progress": "chapter-8",
            "percentage": 0.8,
            "device": "xteink x4",
        },
    )
    assert response.status_code == 200

    response = await client.get("/api/v1/koreader")
    assert response.status_code == 200
    payload = response.json()
    assert len(payload["documents"]) == 1
    assert payload["documents"][0]["linked_book_id"] == tracked.id
    assert payload["documents"][0]["linked_book_title"] == "Filename Title"


async def test_koreader_protocol_sync_links_filename_hash_with_colon_replaced(client, db) -> None:
    tracked = Book(
        slug="filename-title-colon",
        source_url="https://ranobelib.me/ru/book/filename-title-colon",
        title="Filename Title: Test",
        author="Filename Author",
    )
    db.add(tracked)
    await db.commit()
    await db.refresh(tracked)

    filename_hash = hashlib.md5(
        "Filename Author - Filename Title_ Test.epub".encode("utf-8")
    ).hexdigest()

    response = await client.post(
        "/users/create",
        json={"username": "reader-filename-colon", "password": "md5pass"},
    )
    assert response.status_code == 201

    response = await client.put(
        "/syncs/progress",
        headers={
            "x-auth-user": "reader-filename-colon",
            "x-auth-key": "md5pass",
        },
        json={
            "document": filename_hash,
            "progress": "chapter-3",
            "percentage": 0.3,
            "device": "xteink x4",
        },
    )
    assert response.status_code == 200

    response = await client.get("/api/v1/koreader")
    assert response.status_code == 200
    payload = response.json()
    assert len(payload["documents"]) == 1
    assert payload["documents"][0]["linked_book_id"] == tracked.id
    assert payload["documents"][0]["linked_book_title"] == "Filename Title: Test"


async def test_koreader_document_can_be_labeled_in_app(client, db) -> None:
    response = await client.post("/users/create", json={"username": "reader2", "password": "md5pass"})
    assert response.status_code == 201

    response = await client.put(
        "/syncs/progress",
        headers={"x-auth-user": "reader2", "x-auth-key": "md5pass"},
        json={
            "document": "abcdef1234567890abcdef1234567890",
            "progress": "position-15",
            "percentage": 0.15,
            "device": "xteink x4",
        },
    )
    assert response.status_code == 200

    response = await client.get("/api/v1/koreader")
    assert response.status_code == 200
    document_id = response.json()["documents"][0]["id"]

    response = await client.patch(
        f"/api/v1/koreader/documents/{document_id}",
        json={"title": "Manual Device Book", "author": "Side Loaded"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["documents"][0]["title"] == "Manual Device Book"
    assert payload["documents"][0]["author"] == "Side Loaded"

    result = await db.exec(select(KOReaderSyncDocument))
    document = result.one()
    assert document.title == "Manual Device Book"


async def test_koreader_document_can_be_unlinked_and_cleared_in_app(client, db) -> None:
    tracked = Book(
        slug="linked-title",
        source_url="https://ranobelib.me/ru/book/linked-title",
        title="Linked Title",
        author="Tracked Author",
    )
    db.add(tracked)
    await db.commit()
    await db.refresh(tracked)

    response = await client.post("/users/create", json={"username": "reader4", "password": "md5pass"})
    assert response.status_code == 201

    response = await client.put(
        "/syncs/progress",
        headers={"x-auth-user": "reader4", "x-auth-key": "md5pass"},
        json={
            "document": "11111111111111111111111111111111",
            "progress": "position-25",
            "percentage": 0.25,
            "device": "xteink x4",
        },
    )
    assert response.status_code == 200

    response = await client.get("/api/v1/koreader")
    assert response.status_code == 200
    document_id = response.json()["documents"][0]["id"]

    response = await client.patch(
        f"/api/v1/koreader/documents/{document_id}",
        json={"linked_book_id": tracked.id, "title": None, "author": None},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["documents"][0]["linked_book_id"] == tracked.id
    assert payload["documents"][0]["title"] == "Linked Title"
    assert payload["documents"][0]["author"] == "Tracked Author"

    response = await client.patch(
        f"/api/v1/koreader/documents/{document_id}",
        json={"linked_book_id": None, "title": None, "author": None},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["documents"][0]["linked_book_id"] is None
    assert payload["documents"][0]["title"] is None
    assert payload["documents"][0]["author"] is None

    document = await db.get(KOReaderSyncDocument, document_id)
    assert document is not None
    assert document.linked_book_id is None
    assert document.title is None
    assert document.author is None

async def test_koreader_missing_document_returns_empty_payload(client) -> None:
    response = await client.post("/users/create", json={"username": "reader3", "password": "md5pass"})
    assert response.status_code == 201

    response = await client.get(
        "/syncs/progress/missingdoc",
        headers={"x-auth-user": "reader3", "x-auth-key": "md5pass"},
    )
    assert response.status_code == 200
    assert response.json() == {}


async def test_koreader_auth_accepts_app_auth_bridge(client, db, monkeypatch) -> None:
    settings = __import__("app.config", fromlist=["get_settings"]).get_settings()
    original_enabled = settings.auth.enabled
    original_username = settings.auth.username
    original_password = settings.auth.password

    settings.auth.enabled = True
    settings.auth.username = "wnbe"
    settings.auth.password = "Everything13"

    try:
        md5_password = hashlib.md5("Everything13".encode("utf-8")).hexdigest()
        response = await client.get(
            "/users/auth",
            headers={"x-auth-user": "wnbe", "x-auth-key": md5_password},
        )
        assert response.status_code == 200
        assert response.json() == {"authorized": "OK"}
    finally:
        settings.auth.enabled = original_enabled
        settings.auth.username = original_username
        settings.auth.password = original_password


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
                "eng_name": "Preview Book EN",
                "rus_name": "Preview Book RU",
                "publisher": {"name": "Preview Publisher"},
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
    assert payload["title"] == "Preview Book EN"
    assert payload["author"] == "Preview Publisher"
    assert payload["branches"][0]["id"] == "5"
    assert payload["genres"][0]["name"] == "Fantasy"
    assert payload["tags"][0]["name"] == "Academy"


async def test_upload_epubs_imports_multiple_local_titles(client, db, temp_data_dir) -> None:
    response = await client.post(
        "/api/v1/tracking/uploads/epub",
        files=[
            ("files", ("volume-1.epub", build_test_epub_bytes("Uploaded Volume 1", "Uploader One"), "application/epub+zip")),
            ("files", ("volume-2.epub", build_test_epub_bytes("Uploaded Volume 2", "Uploader Two"), "application/epub+zip")),
        ],
    )
    assert response.status_code == 201
    payload = response.json()
    assert len(payload) == 2
    assert payload[0]["title"] == "Uploaded Volume 1"
    assert payload[0]["author"] == "Uploader One"
    assert payload[0]["enabled"] is False
    assert payload[1]["title"] == "Uploaded Volume 2"

    books = (await db.exec(select(Book).where(Book.slug.like("manual-%")).order_by(Book.created_at.asc()))).all()
    assert len(books) == 2

    for book in books:
        artifacts = (await db.exec(select(Artifact).where(Artifact.book_id == book.id, Artifact.format == "epub"))).all()
        assert len(artifacts) == 1
        assert (temp_data_dir / artifacts[0].relative_path).is_file()


async def test_upload_epubs_reuses_existing_manual_title_for_same_file(client, db) -> None:
    file_bytes = build_test_epub_bytes("Uploaded Volume 1", "Uploader One")

    first = await client.post(
        "/api/v1/tracking/uploads/epub",
        files=[("files", ("volume-1.epub", file_bytes, "application/epub+zip"))],
    )
    assert first.status_code == 201
    first_payload = first.json()

    second = await client.post(
        "/api/v1/tracking/uploads/epub",
        files=[("files", ("volume-1-copy.epub", file_bytes, "application/epub+zip"))],
    )
    assert second.status_code == 201
    second_payload = second.json()
    assert second_payload[0]["book_id"] == first_payload[0]["book_id"]

    books = (await db.exec(select(Book).where(Book.source_url.like("manual-upload://epub/%")))).all()
    assert len(books) == 1


async def test_upload_epubs_reupload_backfills_missing_cover(client, db) -> None:
    file_bytes = build_test_epub_bytes_with_cover_page(
        "Uploaded Volume 1",
        "Uploader One",
        cover_bytes=b"cover-backfill",
    )
    file_hash = hashlib.sha256(file_bytes).hexdigest()
    book = Book(
        slug="manual-uploaded-volume-1",
        source_url=f"manual-upload://epub/{file_hash}",
        title="Uploaded Volume 1",
        author="Uploader One",
        available_chapters=1,
        cover_url=None,
    )
    db.add(book)
    await db.commit()
    await db.refresh(book)
    db.add(TrackRule(book_id=book.id, enabled=False, branch_mode="default"))
    db.add(BookState(book_id=book.id))
    await db.commit()

    second = await client.post(
        "/api/v1/tracking/uploads/epub",
        files=[
            (
                "files",
                (
                    "volume-no-cover.epub",
                    file_bytes,
                    "application/epub+zip",
                ),
            )
        ],
    )
    assert second.status_code == 201

    book = await db.get(Book, book.id)
    assert book is not None
    assert book.cover_url is not None


async def test_upload_epubs_extracts_cover_for_local_title(client, db) -> None:
    cover_bytes = b"fake-jpeg-cover"

    response = await client.post(
        "/api/v1/tracking/uploads/epub",
        files=[
            (
                "files",
                (
                    "volume-cover.epub",
                    build_test_epub_bytes("Uploaded Cover Volume", "Uploader Cover", cover_bytes=cover_bytes),
                    "application/epub+zip",
                ),
            )
        ],
    )
    assert response.status_code == 201
    payload = response.json()[0]
    assert payload["cover_url"] is not None
    assert payload["is_manual_upload"] is True

    book = await db.get(Book, payload["book_id"])
    assert book is not None
    assert book.cover_url is not None

    cached_cover = (
        await db.exec(select(BinaryAssetCache).where(BinaryAssetCache.source_url == book.cover_url))
    ).one_or_none()
    assert cached_cover is not None

    cover_response = await client.get(f"/opds/books/{book.id}/cover")
    assert cover_response.status_code == 200
    assert cover_response.content == cover_bytes
    assert cover_response.headers["content-type"].startswith("image/jpeg")


async def test_upload_epubs_extracts_cover_from_cover_page_fallback(client, db) -> None:
    cover_bytes = b"fallback-jpeg-cover"

    response = await client.post(
        "/api/v1/tracking/uploads/epub",
        files=[
            (
                "files",
                (
                    "volume-cover-page.epub",
                    build_test_epub_bytes_with_cover_page(
                        "Uploaded Cover Page Volume",
                        "Uploader Cover",
                        cover_bytes=cover_bytes,
                    ),
                    "application/epub+zip",
                ),
            )
        ],
    )
    assert response.status_code == 201
    payload = response.json()[0]
    assert payload["cover_url"] is not None

    book = await db.get(Book, payload["book_id"])
    assert book is not None
    assert book.cover_url is not None

    cover_response = await client.get(f"/opds/books/{book.id}/cover")
    assert cover_response.status_code == 200
    assert cover_response.content == cover_bytes
    assert cover_response.headers["content-type"].startswith("image/jpeg")


async def test_upload_tracked_book_cover_replaces_existing_cover(client, db) -> None:
    response = await client.post(
        "/api/v1/tracking/uploads/epub",
        files=[
            (
                "files",
                (
                    "volume-cover.epub",
                    build_test_epub_bytes("Uploaded Cover Volume", "Uploader Cover", cover_bytes=b"old-cover"),
                    "application/epub+zip",
                ),
            )
        ],
    )
    assert response.status_code == 201
    payload = response.json()[0]

    update = await client.post(
        f"/api/v1/tracking/books/{payload['book_id']}/cover",
        files=[("file", ("updated-cover.png", b"new-cover", "image/png"))],
    )
    assert update.status_code == 200
    assert update.json()["cover_url"] == f"manual-upload://cover/{payload['book_id']}"

    book = await db.get(Book, payload["book_id"])
    assert book is not None
    assert book.cover_url == f"manual-upload://cover/{payload['book_id']}"

    cached_cover = (
        await db.exec(
            select(BinaryAssetCache).where(
                BinaryAssetCache.source_url == f"manual-upload://cover/{payload['book_id']}"
            )
        )
    ).one_or_none()
    assert cached_cover is not None
    assert cached_cover.media_type == "image/png"
    assert cached_cover.original_name == "updated-cover.png"

    cover_response = await client.get(f"/opds/books/{payload['book_id']}/cover")
    assert cover_response.status_code == 200
    assert cover_response.content == b"new-cover"
    assert cover_response.headers["content-type"].startswith("image/png")


async def test_create_tracked_book_primes_cover_before_epub_build(client, db, monkeypatch) -> None:
    class FakeRanobeLibClient:
        @staticmethod
        def extract_slug_from_url(url: str) -> str | None:
            return "cover-prime-book"

        async def get_novel_info(self, slug: str):
            assert slug == "cover-prime-book"
            return {
                "id": 1,
                "eng_name": "Cover Prime Book",
                "publisher": {"name": "Prime Publisher"},
                "summary": "Summary",
                "cover": {"default": "https://example.com/cover-prime.jpg"},
                "genres": [],
                "tags": [],
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

    async def fake_fetch_binary_asset(_client, url: str):
        assert url == "https://example.com/cover-prime.jpg"
        return ("cover-prime.jpg", b"cover-bytes", "image/jpeg")

    monkeypatch.setattr("app.tracking.router.make_ranobelib_client", fake_make_ranobelib_client)
    monkeypatch.setattr("app.builds.assets.fetch_binary_asset", fake_fetch_binary_asset)

    response = await client.post(
        "/api/v1/tracking/books",
        json={"url": "https://ranobelib.me/ru/book/cover-prime-book"},
    )
    assert response.status_code == 201
    payload = response.json()
    assert payload["title"] == "Cover Prime Book"
    assert payload["author"] == "Prime Publisher"

    result = await db.exec(select(BinaryAssetCache).where(BinaryAssetCache.source_url == "https://example.com/cover-prime.jpg"))
    cached_cover = result.one_or_none()
    assert cached_cover is not None

    response = await client.get(f"/opds/books/{payload['book_id']}/cover")
    assert response.status_code == 200
    assert response.content == b"cover-bytes"
    assert response.headers["content-type"].startswith("image/jpeg")


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


async def test_book_preferences_update_can_edit_title_and_author(client, db) -> None:
    book = Book(
        slug="editable-book",
        source_url="https://ranobelib.me/ru/book/editable-book",
        title="Editable Book",
        author="Original Author",
    )
    db.add(book)
    await db.commit()
    await db.refresh(book)

    db.add(TrackRule(book_id=book.id))
    db.add(BookState(book_id=book.id, last_remote_chapter_key="v1_ch1"))
    await db.commit()

    response = await client.patch(
        f"/api/v1/tracking/books/{book.id}/preferences",
        json={"title": "Edited Book", "author": "Edited Author"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["title"] == "Edited Book"
    assert payload["author"] == "Edited Author"


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


async def test_library_opds_visibility_crud(client, db) -> None:
    book = Book(
        slug="visibility-book",
        source_url="https://ranobelib.me/ru/book/visibility-book",
        title="Visibility Book",
        genres_json='[{"name":"Fantasy","slug":"fantasy"}]',
        tags_json='[{"name":"Academy","slug":"academy"}]',
    )
    db.add(book)
    await db.commit()

    response = await client.get("/api/v1/library/opds-visibility")
    assert response.status_code == 200
    payload = response.json()
    assert payload["genres"][0]["slug"] == "fantasy"
    assert payload["visible_genre_slugs"] == []
    assert payload["visible_tag_slugs"] == []

    response = await client.put(
        "/api/v1/library/opds-visibility",
        json={"visible_genre_slugs": ["fantasy"], "visible_tag_slugs": ["academy"]},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["visible_genre_slugs"] == ["fantasy"]
    assert payload["visible_tag_slugs"] == ["academy"]
