from app.tracking.service import chapter_key


def test_chapter_key() -> None:
    assert chapter_key(1, 2) == "v1_ch2"
    assert chapter_key(None, None) == "v1_ch0"


async def test_healthcheck(client) -> None:
    response = await client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
