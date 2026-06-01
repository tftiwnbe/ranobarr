from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import time

from fastapi import HTTPException, Request, status

from app.config import get_settings

SESSION_COOKIE_NAME = "ranobarr_session"
SESSION_MAX_AGE_SECONDS = 60 * 60 * 24 * 30


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


def auth_credentials_valid(username: str, password: str) -> bool:
    settings = get_settings()
    return secrets.compare_digest(username, settings.auth.username) and secrets.compare_digest(password, settings.auth.password)


def _session_signing_key() -> bytes:
    settings = get_settings()
    return f"{settings.auth.username}:{settings.auth.password}".encode("utf-8")


def create_browser_session_token(username: str) -> str:
    issued_at = str(int(time.time()))
    username_b64 = base64.urlsafe_b64encode(username.encode("utf-8")).decode("ascii").rstrip("=")
    payload = f"{username_b64}.{issued_at}"
    signature = hmac.new(_session_signing_key(), payload.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"{payload}.{signature}"


def authenticated_session_username(request: Request) -> str | None:
    if not is_auth_enabled():
        return None
    token = request.cookies.get(SESSION_COOKIE_NAME)
    if not token:
        return None
    username_b64, sep, remainder = token.partition(".")
    if not sep:
        return None
    issued_at, sep, signature = remainder.partition(".")
    if not sep or not issued_at.isdigit() or not signature:
        return None
    payload = f"{username_b64}.{issued_at}"
    expected_signature = hmac.new(_session_signing_key(), payload.encode("utf-8"), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(signature, expected_signature):
        return None
    if int(time.time()) - int(issued_at) > SESSION_MAX_AGE_SECONDS:
        return None
    padded_username = username_b64 + "=" * (-len(username_b64) % 4)
    try:
        username = base64.urlsafe_b64decode(padded_username.encode("ascii")).decode("utf-8")
    except Exception:
        return None
    settings = get_settings()
    if not secrets.compare_digest(username, settings.auth.username):
        return None
    return username


def ensure_request_authorized(request: Request, *, challenge: bool = False) -> None:
    if not is_auth_enabled():
        return
    if authenticated_session_username(request):
        return
    parsed = _parse_basic_auth(request.headers.get("authorization"))
    if parsed is None:
        raise _unauthorized(challenge=challenge)
    username, password = parsed
    if not auth_credentials_valid(username, password):
        raise _unauthorized(challenge=challenge)


def _unauthorized(*, challenge: bool) -> HTTPException:
    exc = HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")
    if challenge:
        exc.headers = {"WWW-Authenticate": 'Basic realm="Ranobarr"'}
    return exc
