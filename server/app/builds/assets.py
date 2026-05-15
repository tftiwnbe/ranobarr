from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

import httpx
from bs4 import BeautifulSoup
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.builds.media import asset_filename_from_url, resolve_asset_url
from app.builds.storage import asset_file_path, write_binary_asset
from app.models import BinaryAssetCache


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(slots=True)
class CachedBinaryAsset:
    source_url: str
    original_name: str
    media_type: str
    relative_path: str
    content_hash: str


def collect_asset_urls(chapter_html: Iterable[str], cover_url: str | None = None) -> list[str]:
    urls: list[str] = []
    seen: set[str] = set()

    if cover_url:
        resolved = resolve_asset_url(cover_url)
        if resolved not in seen:
            urls.append(resolved)
            seen.add(resolved)

    for html in chapter_html:
        soup = BeautifulSoup(html, "html.parser")
        for img in soup.find_all("img"):
            src = img.get("src")
            if not src:
                continue
            resolved = resolve_asset_url(src)
            if resolved not in seen:
                urls.append(resolved)
                seen.add(resolved)

    return urls


async def ensure_binary_assets_cached(
    session: AsyncSession,
    urls: Iterable[str],
    *,
    fetch_client: httpx.AsyncClient | None = None,
) -> dict[str, CachedBinaryAsset]:
    url_list = list(urls)
    if not url_list:
        return {}

    result = await session.exec(select(BinaryAssetCache).where(BinaryAssetCache.source_url.in_(url_list)))
    existing = {row.source_url: row for row in result.all()}

    created_client = False
    client = fetch_client
    if client is None:
        client = httpx.AsyncClient(timeout=30)
        created_client = True

    try:
        cached: dict[str, CachedBinaryAsset] = {}
        for url in url_list:
            row = existing.get(url)
            if row is not None and asset_file_path(row.relative_path).is_file():
                cached[url] = CachedBinaryAsset(
                    source_url=url,
                    original_name=row.original_name,
                    media_type=row.media_type,
                    relative_path=row.relative_path,
                    content_hash=row.content_hash,
                )
                continue

            fetched = await fetch_binary_asset(client, url)
            if fetched is None:
                continue

            original_name, content, media_type = fetched
            content_hash = hashlib.sha256(content).hexdigest()
            relative_path = write_binary_asset(original_name, content_hash, content)

            if row is None:
                row = BinaryAssetCache(
                    source_url=url,
                    media_type=media_type,
                    original_name=original_name,
                    relative_path=relative_path,
                    content_hash=content_hash,
                )
            else:
                row.media_type = media_type
                row.original_name = original_name
                row.relative_path = relative_path
                row.content_hash = content_hash
                row.fetched_at = utcnow()
                row.updated_at = utcnow()

            session.add(row)
            cached[url] = CachedBinaryAsset(
                source_url=url,
                original_name=original_name,
                media_type=media_type,
                relative_path=relative_path,
                content_hash=content_hash,
            )

        await session.flush()
        return cached
    finally:
        if created_client:
            await client.aclose()


async def fetch_binary_asset(
    client: httpx.AsyncClient,
    url: str,
) -> tuple[str, bytes, str] | None:
    response = await client.get(
        url,
        headers={
            "Referer": "https://ranobelib.me/",
            "User-Agent": "Mozilla/5.0",
        },
    )
    if response.status_code != 200:
        return None

    media_type = response.headers.get("content-type", "application/octet-stream").split(";")[0].strip()
    filename = asset_filename_from_url(url)
    return filename, response.content, media_type
