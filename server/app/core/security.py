from __future__ import annotations

import secrets

from fastapi import HTTPException, Request, status

from app.config import get_settings


def is_auth_enabled() -> bool:
    return get_settings().auth.enabled


def _parse_basic_auth(authorization: str | None) -> tuple[str, str] | None:
    if not authorization:
        return None
    scheme, _, credentials = authorization.partition(" ")
    if scheme.lower() != "basic" or not credentials:
        return None
    try:
        import base64

        decoded = base64.b64decode(credentials).decode("utf-8")
    except Exception:
        return None
    username, sep, password = decoded.partition(":")
    if not sep:
        return None
    return username, password


def ensure_request_authorized(request: Request) -> None:
    if not is_auth_enabled():
        return
    parsed = _parse_basic_auth(request.headers.get("authorization"))
    settings = get_settings()
    if parsed is None:
        raise _unauthorized()
    username, password = parsed
    if not secrets.compare_digest(username, settings.auth.username) or not secrets.compare_digest(
        password, settings.auth.password
    ):
        raise _unauthorized()


def _unauthorized() -> HTTPException:
    exc = HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")
    exc.headers = {"WWW-Authenticate": 'Basic realm="Ranobarr"'}
    return exc
