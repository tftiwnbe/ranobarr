from __future__ import annotations

import json

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.errors import TrackingError
from app.models import AppSetting, CollectionBook, UserCollection
from app.tracking.schemas import (
    CollectionCreateRequest,
    CollectionSummary,
    CollectionUpdateRequest,
    NamedTagSummary,
    OpdsMetadataVisibilityResponse,
    OpdsMetadataVisibilityUpdateRequest,
)
from app.tracking.service import deserialize_named_items, serialize_named_items

OPDS_VISIBLE_GENRES_KEY = "opds_visible_genres"
OPDS_VISIBLE_TAGS_KEY = "opds_visible_tags"


def _slugify_collection_name(value: str) -> str:
    import re

    slug = re.sub(r"[^a-z0-9а-яё]+", "-", value.lower(), flags=re.IGNORECASE)
    return slug.strip("-") or "collection"


async def list_collection_summaries(session: AsyncSession) -> list[CollectionSummary]:
    result = await session.exec(select(UserCollection).order_by(UserCollection.sort_order.asc(), UserCollection.name.asc()))
    collections = result.all()
    membership_result = await session.exec(select(CollectionBook))
    counts: dict[str, int] = {}
    for membership in membership_result.all():
        counts[membership.collection_id] = counts.get(membership.collection_id, 0) + 1

    return [
        CollectionSummary(
            id=collection.id,
            slug=collection.slug,
            name=collection.name,
            description=collection.description,
            sort_order=collection.sort_order,
            book_count=counts.get(collection.id, 0),
        )
        for collection in collections
    ]


async def create_collection(session: AsyncSession, request: CollectionCreateRequest) -> CollectionSummary:
    normalized_name = request.name.strip()
    if not normalized_name:
        raise TrackingError("Collection name is required")

    slug_base = _slugify_collection_name(normalized_name)
    slug = slug_base
    suffix = 2
    while (await session.exec(select(UserCollection).where(UserCollection.slug == slug))).first() is not None:
        slug = f"{slug_base}-{suffix}"
        suffix += 1

    collection = UserCollection(
        slug=slug,
        name=normalized_name,
        description=(request.description or "").strip() or None,
        sort_order=request.sort_order,
    )
    session.add(collection)
    await session.commit()
    await session.refresh(collection)
    return CollectionSummary(
        id=collection.id,
        slug=collection.slug,
        name=collection.name,
        description=collection.description,
        sort_order=collection.sort_order,
        book_count=0,
    )


async def update_collection(
    session: AsyncSession,
    *,
    collection_id: str,
    request: CollectionUpdateRequest,
) -> CollectionSummary:
    collection = await session.get(UserCollection, collection_id)
    if collection is None:
        raise TrackingError("Collection not found")

    field_names = request.model_fields_set
    if "name" in field_names and request.name is not None:
        normalized_name = request.name.strip()
        if not normalized_name:
            raise TrackingError("Collection name is required")
        collection.name = normalized_name
    if "description" in field_names:
        collection.description = (request.description or "").strip() or None
    if "sort_order" in field_names and request.sort_order is not None:
        collection.sort_order = request.sort_order

    session.add(collection)
    await session.commit()

    member_count = len((await session.exec(select(CollectionBook).where(CollectionBook.collection_id == collection.id))).all())
    return CollectionSummary(
        id=collection.id,
        slug=collection.slug,
        name=collection.name,
        description=collection.description,
        sort_order=collection.sort_order,
        book_count=member_count,
    )


async def delete_collection(session: AsyncSession, collection_id: str) -> bool:
    collection = await session.get(UserCollection, collection_id)
    if collection is None:
        return False

    membership_result = await session.exec(select(CollectionBook).where(CollectionBook.collection_id == collection_id))
    for membership in membership_result.all():
        await session.delete(membership)
    await session.delete(collection)
    await session.commit()
    return True


async def get_opds_metadata_visibility(session: AsyncSession) -> OpdsMetadataVisibilityResponse:
    from app.models import Book

    books = (await session.exec(select(Book))).all()
    genres_by_slug: dict[str, NamedTagSummary] = {}
    tags_by_slug: dict[str, NamedTagSummary] = {}
    for book in books:
        for genre in deserialize_named_items(book.genres_json):
            genres_by_slug.setdefault(genre.slug, genre)
        for tag in deserialize_named_items(book.tags_json):
            tags_by_slug.setdefault(tag.slug, tag)

    visible_genres = await _read_named_setting(session, OPDS_VISIBLE_GENRES_KEY)
    visible_tags = await _read_named_setting(session, OPDS_VISIBLE_TAGS_KEY)
    return OpdsMetadataVisibilityResponse(
        genres=sorted(genres_by_slug.values(), key=lambda item: item.name.lower()),
        tags=sorted(tags_by_slug.values(), key=lambda item: item.name.lower()),
        visible_genre_slugs=[item.slug for item in visible_genres],
        visible_tag_slugs=[item.slug for item in visible_tags],
    )


async def update_opds_metadata_visibility(
    session: AsyncSession,
    request: OpdsMetadataVisibilityUpdateRequest,
) -> OpdsMetadataVisibilityResponse:
    visibility = await get_opds_metadata_visibility(session)
    valid_genres = {item.slug: item for item in visibility.genres}
    valid_tags = {item.slug: item for item in visibility.tags}

    selected_genres = [valid_genres[slug] for slug in request.visible_genre_slugs if slug in valid_genres]
    selected_tags = [valid_tags[slug] for slug in request.visible_tag_slugs if slug in valid_tags]

    await _write_named_setting(session, OPDS_VISIBLE_GENRES_KEY, selected_genres)
    await _write_named_setting(session, OPDS_VISIBLE_TAGS_KEY, selected_tags)
    await session.commit()
    return await get_opds_metadata_visibility(session)


async def read_opds_visible_slug_sets(session: AsyncSession) -> tuple[set[str], set[str]]:
    visible_genres = await _read_named_setting(session, OPDS_VISIBLE_GENRES_KEY)
    visible_tags = await _read_named_setting(session, OPDS_VISIBLE_TAGS_KEY)
    return ({item.slug for item in visible_genres}, {item.slug for item in visible_tags})


async def _read_named_setting(session: AsyncSession, key: str) -> list[NamedTagSummary]:
    result = await session.exec(select(AppSetting).where(AppSetting.key == key))
    setting = result.one_or_none()
    if setting is None:
        return []
    try:
        payload = json.loads(setting.value_json)
    except json.JSONDecodeError:
        return []
    return deserialize_named_items(json.dumps(payload, ensure_ascii=False))


async def _write_named_setting(session: AsyncSession, key: str, values: list[NamedTagSummary]) -> None:
    result = await session.exec(select(AppSetting).where(AppSetting.key == key))
    setting = result.one_or_none()
    if setting is None:
        setting = AppSetting(key=key, value_json=serialize_named_items(values))
    else:
        setting.value_json = serialize_named_items(values)
    session.add(setting)
