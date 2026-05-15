from app.builds.content import normalize_cached_payload, normalize_text_string


def test_normalize_text_string() -> None:
    rendered = normalize_text_string("Hello\nworld\n\nNext block")
    assert "<p>Hello world</p>" in rendered
    assert "<p>Next block</p>" in rendered


def test_normalize_cached_doc_payload() -> None:
    payload = {
        "chapter_key": "v1_ch1",
        "volume": "1",
        "number": "1",
        "title": "Chapter 1",
        "content": {
            "type": "doc",
            "content": [
                {"type": "heading", "attrs": {"level": 2}, "content": [{"type": "text", "text": "Heading"}]},
                {
                    "type": "paragraph",
                    "content": [
                        {"type": "text", "text": "Bold", "marks": [{"type": "bold"}]},
                        {"type": "text", "text": " text"},
                    ],
                },
                {
                    "type": "paragraph",
                    "content": [
                        {
                            "type": "image",
                            "attrs": {"images": [{"image": "img-1"}]},
                        }
                    ],
                },
            ],
        },
        "attachments": [{"id": "img-1", "name": "img-1", "url": "https://example.com/image.jpg"}],
    }

    normalized = normalize_cached_payload(payload, content_type="doc")
    assert "<h2>Heading</h2>" in normalized.html_content
    assert "<b>Bold</b>" in normalized.html_content
    assert "https://example.com/image.jpg" in normalized.html_content
