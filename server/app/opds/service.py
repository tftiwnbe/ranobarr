from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from typing import Iterable
from xml.etree.ElementTree import Element, SubElement, tostring, register_namespace

from fastapi import Request
from sqlalchemy import func
from sqlmodel import or_, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.artifacts.service import latest_artifacts_for_books
from app.library.service import read_opds_visible_slug_sets
from app.core.titles import normalize_book_title
from app.models import Artifact, Book, BookState, CollectionBook, UserCollection
from app.tracking.schemas import NamedTagSummary
from app.tracking.service import deserialize_named_items

ATOM_NS = "http://www.w3.org/2005/Atom"
OPDS_NS = "http://opds-spec.org/2010/catalog"
DC_NS = "http://purl.org/dc/terms/"
OPENSEARCH_NS = "http://a9.com/-/spec/opensearch/1.1/"
OPDS_NAVIGATION_TYPE = "application/atom+xml;profile=opds-catalog;kind=navigation"
OPDS_ACQUISITION_TYPE = "application/atom+xml;profile=opds-catalog;kind=acquisition"

register_namespace("", ATOM_NS)
register_namespace("dc", DC_NS)
register_namespace("opds", OPDS_NS)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(slots=True)
class OpdsBookRecord:
    book: Book
    state: BookState | None
    artifact: Artifact
    visible_genres: list[NamedTagSummary]
    visible_tags: list[NamedTagSummary]

    @property
    def updated_at(self) -> datetime:
        return (
            self.artifact.created_at
            or (self.state.last_built_at if self.state and self.state.last_built_at else None)
            or (self.state.last_checked_at if self.state and self.state.last_checked_at else None)
            or self.book.updated_at
            or self.book.created_at
        )


def _isoformat(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _feed_type(kind: str) -> str:
    return OPDS_NAVIGATION_TYPE if kind == "navigation" else OPDS_ACQUISITION_TYPE


def _relative_href(url: str) -> str:
    split = urlsplit(url)
    return urlunsplit(("", "", split.path, split.query, split.fragment))


def _feed_urn(*parts: str) -> str:
    joined = ":".join(part.strip(":") for part in parts if part)
    return f"urn:ranobarr:{joined}"


def _feed_root(title: str, feed_id: str, updated_at: datetime) -> Element:
    feed = Element(f"{{{ATOM_NS}}}feed")
    SubElement(feed, f"{{{ATOM_NS}}}id").text = feed_id
    SubElement(feed, f"{{{ATOM_NS}}}title").text = title
    SubElement(feed, f"{{{ATOM_NS}}}updated").text = _isoformat(updated_at)
    author = SubElement(feed, f"{{{ATOM_NS}}}author")
    SubElement(author, f"{{{ATOM_NS}}}name").text = "Ranobarr"
    return feed


def _feed_link(feed: Element, *, rel: str, href: str, type_value: str | None = None, title: str | None = None):
    attrs = {"rel": rel, "href": href}
    if type_value:
        attrs["type"] = type_value
    if title:
        attrs["title"] = title
    SubElement(feed, f"{{{ATOM_NS}}}link", attrs)


def _entry_link(entry: Element, *, rel: str, href: str, type_value: str | None = None, title: str | None = None):
    attrs = {"rel": rel, "href": href}
    if type_value:
        attrs["type"] = type_value
    if title:
        attrs["title"] = title
    SubElement(entry, f"{{{ATOM_NS}}}link", attrs)


def build_root_feed(request: Request, *, downloadable_count: int, latest_updated_at: datetime | None) -> bytes:
    updated_at = latest_updated_at or utcnow()
    root_href = _relative_href(str(request.url_for("opds_root")))
    feed = _feed_root("Ranobarr Catalog", _feed_urn("opds", "root"), updated_at)
    _feed_link(feed, rel="self", href=root_href, type_value=_feed_type("navigation"))
    _feed_link(feed, rel="start", href=root_href, type_value=_feed_type("navigation"))
    _feed_link(
        feed,
        rel="search",
        href=_relative_href(str(request.url_for("opds_opensearch"))),
        type_value="application/opensearchdescription+xml",
    )

    sections = [
        (
            "All Books",
            _relative_href(str(request.url_for("opds_books_feed"))),
            "Browse all downloadable EPUB books.",
            "acquisition",
        ),
        (
            "Recently Updated",
            _relative_href(f"{request.url_for('opds_books_feed')}?sort=updated"),
            "Newest generated books first.",
            "acquisition",
        ),
        (
            "Favorites",
            _relative_href(str(request.url_for("opds_favorite_books_feed"))),
            "Pinned favorite titles.",
            "acquisition",
        ),
        (
            "Collections",
            _relative_href(str(request.url_for("opds_collection_groups_feed"))),
            "Browse user-defined collections.",
            "navigation",
        ),
        (
            "Genres",
            _relative_href(str(request.url_for("opds_genre_groups_feed"))),
            "Browse books grouped by genre.",
            "navigation",
        ),
        (
            "Tags",
            _relative_href(str(request.url_for("opds_tag_groups_feed"))),
            "Browse books grouped by tag.",
            "navigation",
        ),
    ]

    for title, href, summary, kind in sections:
        entry = SubElement(feed, f"{{{ATOM_NS}}}entry")
        SubElement(entry, f"{{{ATOM_NS}}}id").text = href
        SubElement(entry, f"{{{ATOM_NS}}}title").text = title
        SubElement(entry, f"{{{ATOM_NS}}}updated").text = _isoformat(updated_at)
        SubElement(entry, f"{{{ATOM_NS}}}content", {"type": "text"}).text = summary
        _entry_link(entry, rel="subsection", href=href, type_value=_feed_type(kind))

    SubElement(feed, f"{{{OPDS_NS}}}totalResults").text = str(downloadable_count)
    return tostring(feed, encoding="utf-8", xml_declaration=True)


def build_books_feed(
    request: Request,
    *,
    title: str,
    feed_id: str,
    records: list[OpdsBookRecord],
    total_count: int,
    page: int,
    page_size: int,
    self_href: str,
    start_href: str,
) -> bytes:
    updated_at = max((record.updated_at for record in records), default=utcnow())
    feed = _feed_root(title, feed_id, updated_at)
    _feed_link(feed, rel="self", href=self_href, type_value=_feed_type("acquisition"))
    _feed_link(feed, rel="start", href=start_href, type_value=_feed_type("navigation"))
    _feed_link(
        feed,
        rel="search",
        href=_relative_href(str(request.url_for("opds_opensearch"))),
        type_value="application/opensearchdescription+xml",
    )

    last_page = max((total_count - 1) // page_size + 1, 1)
    if page > 1:
        _feed_link(
            feed,
            rel="previous",
            href=_replace_query(self_href, page=page - 1, page_size=page_size),
            type_value=_feed_type("acquisition"),
        )
    if page < last_page:
        _feed_link(
            feed,
            rel="next",
            href=_replace_query(self_href, page=page + 1, page_size=page_size),
            type_value=_feed_type("acquisition"),
        )
    _feed_link(
        feed,
        rel="first",
        href=_replace_query(self_href, page=1, page_size=page_size),
        type_value=_feed_type("acquisition"),
    )

    for record in records:
        feed.append(build_book_entry(request, record))

    SubElement(feed, f"{{{OPDS_NS}}}totalResults").text = str(total_count)
    SubElement(feed, f"{{{OPENSEARCH_NS}}}itemsPerPage").text = str(page_size)
    SubElement(feed, f"{{{OPENSEARCH_NS}}}startIndex").text = str((page - 1) * page_size + 1)
    return tostring(feed, encoding="utf-8", xml_declaration=True)


def build_book_detail_feed(request: Request, *, record: OpdsBookRecord) -> bytes:
    detail_href = _relative_href(str(request.url_for("opds_book_feed", book_id=record.book.id)))
    feed = _feed_root(normalize_book_title(record.book.title), _feed_urn("opds", "books", record.book.id), record.updated_at)
    _feed_link(feed, rel="self", href=detail_href, type_value=_feed_type("acquisition"))
    _feed_link(feed, rel="start", href=_relative_href(str(request.url_for("opds_root"))), type_value=_feed_type("navigation"))
    feed.append(build_book_entry(request, record))
    return tostring(feed, encoding="utf-8", xml_declaration=True)


def build_book_entry(request: Request, record: OpdsBookRecord) -> Element:
    entry = Element(f"{{{ATOM_NS}}}entry")
    SubElement(entry, f"{{{ATOM_NS}}}id").text = f"urn:ranobarr:book:{record.book.id}"
    SubElement(entry, f"{{{ATOM_NS}}}title").text = normalize_book_title(record.book.title)
    SubElement(entry, f"{{{ATOM_NS}}}updated").text = _isoformat(record.updated_at)

    author = SubElement(entry, f"{{{ATOM_NS}}}author")
    SubElement(author, f"{{{ATOM_NS}}}name").text = record.book.author or "Unknown"

    summary = (record.book.summary or "").strip()
    if summary:
        SubElement(entry, f"{{{ATOM_NS}}}summary", {"type": "text"}).text = summary

    if record.book.status:
        SubElement(
            entry,
            f"{{{ATOM_NS}}}category",
            {"term": record.book.status.lower(), "label": record.book.status},
        )
    for genre in record.visible_genres:
        SubElement(
            entry,
            f"{{{ATOM_NS}}}category",
            {"term": f"genre:{genre.slug}", "label": genre.name},
        )
    for tag in record.visible_tags:
        SubElement(
            entry,
            f"{{{ATOM_NS}}}category",
            {"term": f"tag:{tag.slug}", "label": tag.name},
        )

    acquisition_href = _relative_href(str(request.url_for("opds_acquire_epub", book_id=record.book.id)))
    detail_href = _relative_href(str(request.url_for("opds_book_feed", book_id=record.book.id)))
    cover_href = _relative_href(str(request.url_for("opds_cover", book_id=record.book.id)))

    _entry_link(entry, rel="alternate", href=detail_href, type_value=_feed_type("acquisition"))
    _entry_link(
        entry,
        rel="http://opds-spec.org/acquisition",
        href=acquisition_href,
        type_value="application/epub+zip",
        title="Download EPUB",
    )
    if record.book.cover_url:
        _entry_link(entry, rel="http://opds-spec.org/image", href=cover_href, type_value="image/*")
        _entry_link(entry, rel="http://opds-spec.org/image/thumbnail", href=cover_href, type_value="image/*")

    content_lines = [f"{record.artifact.chapter_count} chapters"]
    if record.state and record.state.last_remote_chapter_key:
        content_lines.append(f"Latest chapter: {record.state.last_remote_chapter_key}")
    SubElement(entry, f"{{{ATOM_NS}}}content", {"type": "text"}).text = " • ".join(content_lines)
    return entry


def build_opensearch_description(request: Request) -> bytes:
    root = Element(f"{{{OPENSEARCH_NS}}}OpenSearchDescription")
    SubElement(root, f"{{{OPENSEARCH_NS}}}ShortName").text = "Ranobarr"
    SubElement(root, f"{{{OPENSEARCH_NS}}}Description").text = "Search downloadable Ranobarr books"
    SubElement(
        root,
        f"{{{OPENSEARCH_NS}}}Url",
        {
            "type": OPDS_ACQUISITION_TYPE,
            "template": f"{_relative_href(str(request.url_for('opds_search_feed')))}?q={{searchTerms}}",
        },
    )
    return tostring(root, encoding="utf-8", xml_declaration=True)


async def list_downloadable_books(
    session: AsyncSession,
    *,
    page: int,
    page_size: int,
    sort: str,
    query: str | None = None,
    favorites_only: bool = False,
    current_only: bool = False,
    collection_id: str | None = None,
) -> tuple[list[OpdsBookRecord], int]:
    visible_genre_slugs, visible_tag_slugs = await read_opds_visible_slug_sets(session)
    latest_epub_subquery = (
        select(Artifact.book_id)
        .where(Artifact.format == "epub")
        .group_by(Artifact.book_id)
        .subquery()
    )

    book_query = (
        select(Book, BookState)
        .join(latest_epub_subquery, latest_epub_subquery.c.book_id == Book.id)
        .outerjoin(BookState, BookState.book_id == Book.id)
    )
    count_query = (
        select(func.count())
        .select_from(Book)
        .join(latest_epub_subquery, latest_epub_subquery.c.book_id == Book.id)
    )

    if query:
        like = f"%{query.strip()}%"
        predicate = or_(Book.title.ilike(like), Book.slug.ilike(like), Book.author.ilike(like))
        book_query = book_query.where(predicate)
        count_query = count_query.where(predicate)
    if favorites_only:
        book_query = book_query.where(Book.is_favorite.is_(True))
        count_query = count_query.where(Book.is_favorite.is_(True))
    if current_only:
        book_query = book_query.where(Book.is_current.is_(True))
        count_query = count_query.where(Book.is_current.is_(True))
    if collection_id:
        collection_subquery = select(CollectionBook.book_id).where(CollectionBook.collection_id == collection_id).subquery()
        book_query = book_query.join(collection_subquery, collection_subquery.c.book_id == Book.id)
        count_query = count_query.join(collection_subquery, collection_subquery.c.book_id == Book.id)

    if sort == "title":
        book_query = book_query.order_by(Book.title.asc(), Book.id.asc())
    else:
        updated_order = func.coalesce(
            BookState.last_built_at,
            BookState.last_checked_at,
            Book.updated_at,
            Book.created_at,
        )
        book_query = book_query.order_by(updated_order.desc(), Book.title.asc())

    total_count = int((await session.exec(count_query)).one())

    result = await session.exec(book_query.offset((page - 1) * page_size).limit(page_size))
    rows = result.all()
    books = [row[0] for row in rows]
    states_by_book_id = {row[0].id: row[1] for row in rows}
    artifact_map = await latest_artifacts_for_books(
        session,
        book_ids=[book.id for book in books],
        format_name="epub",
    )

    records = [
        OpdsBookRecord(
            book=book,
            state=states_by_book_id.get(book.id),
            artifact=artifact_map[book.id],
            visible_genres=_metadata_items(book, "genres", visible_genre_slugs),
            visible_tags=_metadata_items(book, "tags", visible_tag_slugs),
        )
        for book in books
        if book.id in artifact_map
    ]
    return records, total_count


async def get_downloadable_book_record(
    session: AsyncSession,
    *,
    book_id: str,
) -> OpdsBookRecord | None:
    result = await session.exec(
        select(Book, BookState)
        .where(Book.id == book_id)
        .outerjoin(BookState, BookState.book_id == Book.id)
    )
    row = result.one_or_none()
    if row is None:
        return None

    artifact = await latest_artifacts_for_books(
        session,
        book_ids=[book_id],
        format_name="epub",
    )
    book, state = row
    latest = artifact.get(book_id)
    if latest is None:
        return None
    visible_genre_slugs, visible_tag_slugs = await read_opds_visible_slug_sets(session)
    return OpdsBookRecord(
        book=book,
        state=state,
        artifact=latest,
        visible_genres=_metadata_items(book, "genres", visible_genre_slugs),
        visible_tags=_metadata_items(book, "tags", visible_tag_slugs),
    )


async def list_grouped_metadata(
    session: AsyncSession,
    *,
    field_name: str,
) -> list[tuple[NamedTagSummary, int]]:
    records, _ = await list_downloadable_books(
        session,
        page=1,
        page_size=1000,
        sort="title",
    )
    counts: dict[str, tuple[NamedTagSummary, set[str]]] = {}
    for record in records:
        items = record.visible_genres if field_name == "genres" else record.visible_tags
        for item in items:
            current = counts.get(item.slug)
            if current is None:
                counts[item.slug] = (item, {record.book.id})
            else:
                current[1].add(record.book.id)

    grouped = [(item, len(book_ids)) for item, book_ids in counts.values()]
    grouped.sort(key=lambda row: (-row[1], row[0].name.lower()))
    return grouped


async def list_downloadable_books_by_group(
    session: AsyncSession,
    *,
    field_name: str,
    group_slug: str,
    page: int,
    page_size: int,
) -> tuple[list[OpdsBookRecord], int, str | None]:
    records, _ = await list_downloadable_books(
        session,
        page=1,
        page_size=1000,
        sort="title",
    )
    filtered: list[OpdsBookRecord] = []
    group_name: str | None = None
    for record in records:
        items = record.visible_genres if field_name == "genres" else record.visible_tags
        for item in items:
            if item.slug == group_slug:
                group_name = item.name
                filtered.append(record)
                break

    total_count = len(filtered)
    start = (page - 1) * page_size
    end = start + page_size
    return filtered[start:end], total_count, group_name


async def list_collection_groups(session: AsyncSession) -> list[tuple[UserCollection, int]]:
    collections = (await session.exec(select(UserCollection).order_by(UserCollection.sort_order.asc(), UserCollection.name.asc()))).all()
    memberships = (await session.exec(select(CollectionBook))).all()
    counts: dict[str, int] = {}
    for membership in memberships:
        counts[membership.collection_id] = counts.get(membership.collection_id, 0) + 1
    return [(collection, counts.get(collection.id, 0)) for collection in collections]


async def get_collection(session: AsyncSession, collection_id: str) -> UserCollection | None:
    return await session.get(UserCollection, collection_id)


def build_group_feed(
    request: Request,
    *,
    title: str,
    route_name: str,
    entries: list[tuple[NamedTagSummary, int]] | list[tuple[UserCollection, int]],
    self_href: str,
) -> bytes:
    feed = _feed_root(title, self_href, utcnow())
    _feed_link(feed, rel="self", href=self_href, type_value=_feed_type("navigation"))
    _feed_link(feed, rel="start", href=_relative_href(str(request.url_for("opds_root"))), type_value=_feed_type("navigation"))
    for item, count in entries:
        if isinstance(item, UserCollection):
            href = _relative_href(str(request.url_for(route_name, collection_id=item.id)))
            entry_title = item.name
        else:
            href = _relative_href(str(request.url_for(route_name, group_slug=item.slug)))
            entry_title = item.name
        entry = SubElement(feed, f"{{{ATOM_NS}}}entry")
        SubElement(entry, f"{{{ATOM_NS}}}id").text = href
        SubElement(entry, f"{{{ATOM_NS}}}title").text = entry_title
        SubElement(entry, f"{{{ATOM_NS}}}updated").text = _isoformat(utcnow())
        SubElement(
            entry,
            f"{{{ATOM_NS}}}content",
            {"type": "text"},
        ).text = f"{count} downloadable title{'s' if count != 1 else ''}"
        _entry_link(entry, rel="subsection", href=href, type_value=_feed_type("acquisition"))
        _entry_link(entry, rel="alternate", href=href, type_value=_feed_type("acquisition"))
    return tostring(feed, encoding="utf-8", xml_declaration=True)


def _replace_query(href: str, **params: int) -> str:
    split = urlsplit(href)
    current = dict(parse_qsl(split.query, keep_blank_values=True))
    current.update({key: str(value) for key, value in params.items()})
    return urlunsplit(("", "", split.path, urlencode(current), split.fragment))


def _metadata_items(book: Book, field_name: str, allowed_slugs: set[str]) -> list[NamedTagSummary]:
    if field_name == "genres":
        items = deserialize_named_items(book.genres_json)
        return [item for item in items if item.slug in allowed_slugs]
    if field_name == "tags":
        items = deserialize_named_items(book.tags_json)
        return [item for item in items if item.slug in allowed_slugs]
    raise ValueError(f"Unsupported metadata field: {field_name}")
