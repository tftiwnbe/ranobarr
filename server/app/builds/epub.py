from __future__ import annotations

import mimetypes
from pathlib import Path
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup
from ebooklib import epub

from app.builds.content import NormalizedChapter


async def build_epub_bytes(
    *,
    identifier: str,
    title: str,
    author: str | None,
    summary: str | None,
    cover_url: str | None,
    chapters: list[NormalizedChapter],
) -> bytes:
    book = epub.EpubBook()
    book.set_identifier(identifier)
    book.set_title(title)
    book.set_language("ru")
    if author:
        book.add_author(author)
    if summary:
        book.add_metadata("DC", "description", summary)

    async with httpx.AsyncClient(timeout=30) as client:
        if cover_url:
            cover = await fetch_binary_asset(client, cover_url)
            if cover is not None:
                cover_name, cover_bytes, _ = cover
                book.set_cover(cover_name, cover_bytes, create_page=True)

        spine: list[epub.EpubHtml | str] = ["nav"]
        toc: list[epub.EpubHtml] = []
        image_counter = 0
        embedded_images: dict[str, str] = {}

        for chapter in chapters:
            soup = BeautifulSoup(chapter.html_content, "html.parser")
            for img in soup.find_all("img"):
                src = img.get("src")
                if not src:
                    continue

                if src not in embedded_images:
                    fetched = await fetch_binary_asset(client, src)
                    if fetched is not None:
                        original_name, content, media_type = fetched
                        ext = guess_extension(media_type, original_name)
                        image_counter += 1
                        item_path = f"images/{chapter.chapter_key}-{image_counter}{ext}"
                        image_item = epub.EpubItem(
                            uid=f"image-{chapter.chapter_key}-{image_counter}",
                            file_name=item_path,
                            media_type=media_type,
                            content=content,
                        )
                        book.add_item(image_item)
                        embedded_images[src] = item_path

                if src in embedded_images:
                    img["src"] = embedded_images[src]

            chapter_title = chapter_title_text(chapter)
            epub_chapter = epub.EpubHtml(
                title=chapter_title,
                file_name=f"{chapter.chapter_key}.xhtml",
                lang="ru",
            )
            epub_chapter.set_content(f"<h1>{chapter_title}</h1>{str(soup)}")
            book.add_item(epub_chapter)
            spine.append(epub_chapter)
            toc.append(epub_chapter)

        book.toc = tuple(toc)
        book.spine = spine
        book.add_item(epub.EpubNcx())
        book.add_item(epub.EpubNav())

        temp_path = Path("/tmp") / f"{identifier}.epub"
        epub.write_epub(str(temp_path), book, {})
        data = temp_path.read_bytes()
        temp_path.unlink(missing_ok=True)
        return data


def chapter_title_text(chapter: NormalizedChapter) -> str:
    base = f"Volume {chapter.volume} Chapter {chapter.number}"
    if chapter.title:
        return f"{base} - {chapter.title}"
    return base


async def fetch_binary_asset(
    client: httpx.AsyncClient,
    url: str,
) -> tuple[str, bytes, str] | None:
    resolved_url = resolve_asset_url(url)
    response = await client.get(
        resolved_url,
        headers={
            "Referer": "https://ranobelib.me/",
            "User-Agent": "Mozilla/5.0",
        },
    )
    if response.status_code != 200:
        return None

    media_type = response.headers.get("content-type", "application/octet-stream").split(";")[0].strip()
    filename = asset_filename_from_url(resolved_url)
    return filename, response.content, media_type


def resolve_asset_url(url: str) -> str:
    if url.startswith("//"):
        return f"https:{url}"
    if url.startswith("/"):
        return f"https://ranobelib.me{url}"
    return url


def asset_filename_from_url(url: str) -> str:
    path = urlparse(url).path
    name = Path(path).name
    return name or "asset.bin"


def guess_extension(media_type: str, fallback_name: str) -> str:
    suffix = Path(fallback_name).suffix
    if suffix:
        return suffix
    guessed = mimetypes.guess_extension(media_type)
    return guessed or ".bin"
