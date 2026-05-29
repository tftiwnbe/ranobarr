from __future__ import annotations

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.errors import TrackingError
from app.models import CollectionBook, UserCollection
from app.tracking.schemas import CollectionCreateRequest, CollectionSummary, CollectionUpdateRequest


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
