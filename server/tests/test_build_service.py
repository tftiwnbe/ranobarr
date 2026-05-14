from app.builds.service import detect_content_type, hash_payload


def test_detect_content_type() -> None:
    assert detect_content_type("<p>hello</p>") == "html"
    assert detect_content_type("hello") == "text"
    assert detect_content_type([{"type": "paragraph"}]) == "doc"


def test_hash_payload_stable() -> None:
    payload = {"b": 2, "a": 1}
    assert hash_payload(payload) == hash_payload({"a": 1, "b": 2})
