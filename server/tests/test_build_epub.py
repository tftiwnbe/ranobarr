from app.builds.content import NormalizedChapter
from app.builds.epub import chapter_title_text
from app.builds.media import asset_filename_from_url, resolve_asset_url


def test_resolve_asset_url() -> None:
    assert resolve_asset_url("/uploads/test.jpg") == "https://ranobelib.me/uploads/test.jpg"
    assert resolve_asset_url("//cdn.example.com/a.jpg") == "https://cdn.example.com/a.jpg"
    assert resolve_asset_url("https://example.com/a.jpg") == "https://example.com/a.jpg"


def test_asset_filename_from_url() -> None:
    assert asset_filename_from_url("https://example.com/a/b/c.jpg") == "c.jpg"


def test_chapter_title_text() -> None:
    chapter = NormalizedChapter(
        chapter_key="v1_ch1",
        volume="1",
        number="1",
        title="Opening",
        branch_id=None,
        branch_name=None,
        content_type="html",
        html_content="<p>Hello</p>",
        attachments=[],
    )
    assert chapter_title_text(chapter) == "Volume 1 Chapter 1 - Opening"
