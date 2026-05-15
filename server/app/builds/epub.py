from __future__ import annotations

from bs4 import BeautifulSoup
from ebooklib import epub

from app.builds.media import guess_extension, resolve_asset_url
from app.builds.content import NormalizedChapter
from app.builds.assets import CachedBinaryAsset
from app.builds.storage import asset_file_path


async def build_epub_bytes(
    *,
    identifier: str,
    title: str,
    author: str | None,
    summary: str | None,
    cover_url: str | None,
    chapters: list[NormalizedChapter],
    binary_assets: dict[str, CachedBinaryAsset],
) -> bytes:
    book = epub.EpubBook()
    book.set_identifier(identifier)
    book.set_title(title)
    book.set_language("ru")
    if author:
        book.add_author(author)
    if summary:
        book.add_metadata("DC", "description", summary)

    if cover_url:
        resolved_cover = resolve_asset_url(cover_url)
        cover_asset = binary_assets.get(resolved_cover)
        if cover_asset is not None:
            cover_bytes = asset_file_path(cover_asset.relative_path).read_bytes()
            book.set_cover(cover_asset.original_name, cover_bytes, create_page=True)

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

            resolved_src = resolve_asset_url(src)
            if resolved_src not in embedded_images:
                cached_asset = binary_assets.get(resolved_src)
                if cached_asset is not None:
                    content = asset_file_path(cached_asset.relative_path).read_bytes()
                    ext = guess_extension(cached_asset.media_type, cached_asset.original_name)
                    image_counter += 1
                    item_path = f"images/{chapter.chapter_key}-{image_counter}{ext}"
                    image_item = epub.EpubItem(
                        uid=f"image-{chapter.chapter_key}-{image_counter}",
                        file_name=item_path,
                        media_type=cached_asset.media_type,
                        content=content,
                    )
                    book.add_item(image_item)
                    embedded_images[resolved_src] = item_path

            if resolved_src in embedded_images:
                img["src"] = embedded_images[resolved_src]

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

    from pathlib import Path

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
