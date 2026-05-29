import base64

from app.config import get_settings


def _basic_auth_header(username: str, password: str) -> dict[str, str]:
    token = base64.b64encode(f"{username}:{password}".encode("utf-8")).decode("ascii")
    return {"Authorization": f"Basic {token}"}


async def test_basic_auth_protects_api_and_opds(client) -> None:
    settings = get_settings()
    original_enabled = settings.auth.enabled
    original_username = settings.auth.username
    original_password = settings.auth.password
    settings.auth.enabled = True
    settings.auth.username = "reader"
    settings.auth.password = "secret"

    try:
        response = await client.get("/api/v1/jobs")
        assert response.status_code == 401
        assert response.headers["www-authenticate"] == 'Basic realm="Ranobarr"'

        response = await client.get("/opds")
        assert response.status_code == 401

        response = await client.get("/api/v1/jobs", headers=_basic_auth_header("reader", "secret"))
        assert response.status_code == 200

        response = await client.get("/opds", headers=_basic_auth_header("reader", "secret"))
        assert response.status_code == 200
        assert response.headers["cache-control"] == "private, no-store"
    finally:
        settings.auth.enabled = original_enabled
        settings.auth.username = original_username
        settings.auth.password = original_password
