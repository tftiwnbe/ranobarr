import json
from pathlib import Path
from xml.etree import ElementTree as ET

from sqlmodel import select

from app.library.service import update_opds_metadata_visibility
from app.models import Artifact, BinaryAssetCache, Book, BookState, CollectionBook, UserCollection
from app.tracking.schemas import OpdsMetadataVisibilityUpdateRequest

ATOM_NS = {"atom": "http://www.w3.org/2005/Atom"}


async def create_downloadable_book(
    db,
    temp_data_dir: Path,
    *,
    slug: str,
    title: str,
    author: str = "Author",
    summary: str = "Summary",
    chapter_count: int = 2,
    cover_url: str | None = "https://example.com/cover.jpg",
    genres: list[dict[str, str]] | None = None,
    tags: list[dict[str, str]] | None = None,
) -> tuple[Book, Artifact]:
    book = Book(
        slug=slug,
        source_url=f"https://ranobelib.me/ru/book/{slug}",
        title=title,
        author=author,
        summary=summary,
        cover_url=cover_url,
        genres_json=json.dumps(genres or [], ensure_ascii=False),
        tags_json=json.dumps(tags or [], ensure_ascii=False),
        opds_visible_genres_json=json.dumps(genres or [], ensure_ascii=False),
        opds_visible_tags_json=json.dumps(tags or [], ensure_ascii=False),
        available_chapters=chapter_count,
    )
    db.add(book)
    await db.commit()
    await db.refresh(book)

    db.add(
        BookState(
            book_id=book.id,
            last_remote_chapter_key=f"v1_ch{chapter_count}",
        )
    )

    artifact_path = temp_data_dir / "artifacts" / book.id / "book.epub"
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    artifact_path.write_bytes(f"{title}-epub".encode("utf-8"))

    artifact = Artifact(
        book_id=book.id,
        format="epub",
        relative_path=str(artifact_path.relative_to(temp_data_dir)),
        chapter_count=chapter_count,
        file_size_bytes=artifact_path.stat().st_size,
    )
    db.add(artifact)
    await db.commit()
    await db.refresh(artifact)
    return book, artifact


async def test_opds_root_exposes_navigation_sections(client, db, temp_data_dir) -> None:
    await create_downloadable_book(
        db,
        temp_data_dir,
        slug="alpha-book",
        title="Alpha Book",
    )

    response = await client.get("/opds")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/atom+xml")

    root = ET.fromstring(response.content)
    assert root.findtext("atom:title", namespaces=ATOM_NS) == "Ranobarr Catalog"

    titles = [entry.findtext("atom:title", namespaces=ATOM_NS) for entry in root.findall("atom:entry", ATOM_NS)]
    assert titles == ["All Books", "Recently Updated", "Favorites", "Collections", "Genres", "Tags"]

    links = {link.attrib["rel"]: link.attrib["href"] for link in root.findall("atom:link", ATOM_NS)}
    assert links["self"].endswith("/opds")
    assert links["search"].endswith("/opds/opensearch.xml")


async def test_opds_books_and_search_only_include_downloadable_titles(client, db, temp_data_dir) -> None:
    downloadable, _ = await create_downloadable_book(
        db,
        temp_data_dir,
        slug="alpha-book",
        title="Alpha Book (Новелла)",
    )
    db.add(
        Book(
            slug="beta-book",
            source_url="https://ranobelib.me/ru/book/beta-book",
            title="Beta Book",
            available_chapters=1,
        )
    )
    await db.commit()

    response = await client.get("/opds/books")
    assert response.status_code == 200
    root = ET.fromstring(response.content)
    titles = [entry.findtext("atom:title", namespaces=ATOM_NS) for entry in root.findall("atom:entry", ATOM_NS)]
    assert titles == ["Alpha Book"]

    response = await client.get("/opds/search?q=alpha")
    assert response.status_code == 200
    search_root = ET.fromstring(response.content)
    titles = [entry.findtext("atom:title", namespaces=ATOM_NS) for entry in search_root.findall("atom:entry", ATOM_NS)]
    assert titles == ["Alpha Book"]

    response = await client.get("/opds/search?q=beta")
    assert response.status_code == 200
    search_root = ET.fromstring(response.content)
    assert search_root.findall("atom:entry", ATOM_NS) == []


async def test_opds_book_detail_and_epub_acquisition(client, db, temp_data_dir) -> None:
    book, artifact = await create_downloadable_book(
        db,
        temp_data_dir,
        slug="detail-book",
        title="Detail Book",
        chapter_count=7,
    )

    response = await client.get(f"/opds/books/{book.id}")
    assert response.status_code == 200
    root = ET.fromstring(response.content)
    entry = root.find("atom:entry", ATOM_NS)
    assert entry is not None
    assert entry.findtext("atom:title", namespaces=ATOM_NS) == "Detail Book"
    acquisition_links = [
        link.attrib["href"]
        for link in entry.findall("atom:link", ATOM_NS)
        if link.attrib.get("rel") == "http://opds-spec.org/acquisition"
    ]
    assert acquisition_links == [f"/opds/books/{book.id}/acquire/epub"]

    response = await client.get(f"/opds/books/{book.id}/acquire/epub")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/epub+zip")
    assert "filename*=utf-8''Author%20-%20Detail%20Book.epub" in response.headers[
        "content-disposition"
    ]
    assert response.content == b"Detail Book-epub"

    response = await client.get(f"/api/v1/artifacts/{artifact.id}/download")
    assert response.status_code == 200
    assert "filename*=utf-8''Author%20-%20Detail%20Book.epub" in response.headers[
        "content-disposition"
    ]


async def test_opds_cover_streams_cached_image(client, db, temp_data_dir) -> None:
    book, _ = await create_downloadable_book(
        db,
        temp_data_dir,
        slug="cover-book",
        title="Cover Book",
        cover_url="https://example.com/cover-book.jpg",
    )
    cover_path = temp_data_dir / "cache" / "assets" / "cover-book.jpg"
    cover_path.parent.mkdir(parents=True, exist_ok=True)
    cover_path.write_bytes(b"image-bytes")

    db.add(
        BinaryAssetCache(
            source_url="https://example.com/cover-book.jpg",
            media_type="image/jpeg",
            original_name="cover-book.jpg",
            relative_path=str(cover_path.relative_to(temp_data_dir)),
            content_hash="hash-cover",
        )
    )
    await db.commit()

    response = await client.get(f"/opds/books/{book.id}/cover")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("image/jpeg")
    assert response.content == b"image-bytes"


async def test_opds_group_feeds_expose_genres_and_tags(client, db, temp_data_dir) -> None:
    await create_downloadable_book(
        db,
        temp_data_dir,
        slug="group-book",
        title="Group Book",
        genres=[{"name": "Fantasy", "slug": "fantasy"}],
        tags=[{"name": "Academy", "slug": "academy"}],
    )

    response = await client.get("/opds/genres")
    assert response.status_code == 200
    root = ET.fromstring(response.content)
    genre_titles = [entry.findtext("atom:title", namespaces=ATOM_NS) for entry in root.findall("atom:entry", ATOM_NS)]
    assert genre_titles == []

    response = await client.put(
        "/api/v1/library/opds-visibility",
        json={"visible_genre_slugs": ["fantasy"], "visible_tag_slugs": ["academy"]},
    )
    assert response.status_code == 200

    response = await client.get("/opds/genres")
    assert response.status_code == 200
    root = ET.fromstring(response.content)
    genre_titles = [entry.findtext("atom:title", namespaces=ATOM_NS) for entry in root.findall("atom:entry", ATOM_NS)]
    assert genre_titles == ["Fantasy"]

    response = await client.get("/opds/genres/fantasy")
    assert response.status_code == 200
    root = ET.fromstring(response.content)
    titles = [entry.findtext("atom:title", namespaces=ATOM_NS) for entry in root.findall("atom:entry", ATOM_NS)]
    assert titles == ["Group Book"]

    response = await client.get("/opds/tags")
    assert response.status_code == 200
    root = ET.fromstring(response.content)
    tag_titles = [entry.findtext("atom:title", namespaces=ATOM_NS) for entry in root.findall("atom:entry", ATOM_NS)]
    assert tag_titles == ["Academy"]


async def test_opds_acquisition_marks_last_downloaded(client, db, temp_data_dir) -> None:
    book, _ = await create_downloadable_book(
        db,
        temp_data_dir,
        slug="download-book",
        title="Download Book",
    )
    response = await client.get(f"/opds/books/{book.id}/acquire/epub")
    assert response.status_code == 200

    state = (await db.exec(select(BookState).where(BookState.book_id == book.id))).one()
    assert state.last_downloaded_at is not None


async def test_opds_current_favorites_and_collections_use_filtered_library_state(client, db, temp_data_dir) -> None:
    favorite_book, _ = await create_downloadable_book(
        db,
        temp_data_dir,
        slug="favorite-book",
        title="Favorite Book",
        genres=[{"name": "Боевик", "slug": "old-cyrillic"}],
        tags=[{"name": "Magic", "slug": "magic"}],
    )
    favorite_book.is_favorite = True
    favorite_book.is_current = True
    favorite_book.opds_visible_tags_json = json.dumps([], ensure_ascii=False)
    db.add(favorite_book)

    hidden_book, _ = await create_downloadable_book(
        db,
        temp_data_dir,
        slug="hidden-book",
        title="Hidden Book",
        genres=[{"name": "Fantasy", "slug": "fantasy"}],
    )
    collection = UserCollection(slug="featured", name="Featured")
    db.add(collection)
    await db.commit()
    await db.refresh(collection)
    db.add(CollectionBook(collection_id=collection.id, book_id=favorite_book.id))
    await db.commit()
    await update_opds_metadata_visibility(
        db,
        OpdsMetadataVisibilityUpdateRequest(
            visible_genre_slugs=["old-cyrillic"],
            visible_tag_slugs=[],
        ),
    )

    response = await client.get("/opds/current")
    assert response.status_code == 200
    root = ET.fromstring(response.content)
    titles = [entry.findtext("atom:title", namespaces=ATOM_NS) for entry in root.findall("atom:entry", ATOM_NS)]
    assert titles == ["Favorite Book"]

    response = await client.get("/opds/favorites")
    assert response.status_code == 200
    root = ET.fromstring(response.content)
    titles = [entry.findtext("atom:title", namespaces=ATOM_NS) for entry in root.findall("atom:entry", ATOM_NS)]
    assert titles == ["Favorite Book"]

    response = await client.get("/opds/collections")
    assert response.status_code == 200
    root = ET.fromstring(response.content)
    titles = [entry.findtext("atom:title", namespaces=ATOM_NS) for entry in root.findall("atom:entry", ATOM_NS)]
    assert titles == ["Featured"]

    response = await client.get(f"/opds/collections/{collection.id}")
    assert response.status_code == 200
    root = ET.fromstring(response.content)
    titles = [entry.findtext("atom:title", namespaces=ATOM_NS) for entry in root.findall("atom:entry", ATOM_NS)]
    assert titles == ["Favorite Book"]

    detail = ET.fromstring((await client.get(f"/opds/books/{favorite_book.id}")).content)
    entry = detail.find("atom:entry", ATOM_NS)
    assert entry is not None
