from pydantic import BaseModel, Field
from fastapi import APIRouter, HTTPException, Request, Response, status

from app.core.security import (
    SESSION_COOKIE_NAME,
    SESSION_MAX_AGE_SECONDS,
    auth_credentials_valid,
    authenticated_session_username,
    create_browser_session_token,
    is_auth_enabled,
)

router = APIRouter(tags=["system"])


class BrowserAuthSessionResponse(BaseModel):
    auth_enabled: bool
    authenticated: bool
    username: str | None = None


class BrowserAuthLoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=240)
    password: str = Field(min_length=1, max_length=240)
    remember_me: bool = True


@router.get("/health")
async def healthcheck() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/api/v1/app-auth/session", response_model=BrowserAuthSessionResponse)
async def get_browser_auth_session(request: Request) -> BrowserAuthSessionResponse:
    if not is_auth_enabled():
        return BrowserAuthSessionResponse(auth_enabled=False, authenticated=True)
    username = authenticated_session_username(request)
    return BrowserAuthSessionResponse(
        auth_enabled=True,
        authenticated=username is not None,
        username=username,
    )


@router.post("/api/v1/app-auth/login", response_model=BrowserAuthSessionResponse)
async def login_browser_session(request: BrowserAuthLoginRequest, response: Response) -> BrowserAuthSessionResponse:
    if not is_auth_enabled():
        return BrowserAuthSessionResponse(auth_enabled=False, authenticated=True)
    if not auth_credentials_valid(request.username, request.password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid username or password")
    max_age = SESSION_MAX_AGE_SECONDS if request.remember_me else None
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=create_browser_session_token(request.username),
        max_age=max_age,
        httponly=True,
        samesite="lax",
        secure=False,
        path="/",
    )
    return BrowserAuthSessionResponse(auth_enabled=True, authenticated=True, username=request.username)


@router.post("/api/v1/app-auth/logout", response_model=BrowserAuthSessionResponse)
async def logout_browser_session(response: Response) -> BrowserAuthSessionResponse:
    response.delete_cookie(SESSION_COOKIE_NAME, path="/")
    return BrowserAuthSessionResponse(auth_enabled=is_auth_enabled(), authenticated=False)
