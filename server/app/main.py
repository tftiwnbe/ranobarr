import uvicorn
from contextlib import asynccontextmanager
import logging
import time
from typing import Callable

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.artifacts.router import router as artifacts_router
from app.config import get_settings
from app.core.database import run_async_upgrade, sessionmanager
from app.core.jobs import job_runtime
from app.core.logging import configure_logging
from app.core.security import ensure_request_authorized, is_auth_enabled
from app.jobs.router import router as jobs_router
from app.koreader.router import app_router as koreader_app_router
from app.koreader.router import router as koreader_router
from app.library.router import router as library_router
from app.opds.router import router as opds_router
from app.source_auth.router import router as source_auth_router
from app.system.router import router as system_router
from app.tracking.router import router as tracking_router


@asynccontextmanager
async def lifespan(_app: FastAPI):
    settings = get_settings()
    settings.app.data_dir.mkdir(parents=True, exist_ok=True)
    settings.app.artifacts_dir.mkdir(parents=True, exist_ok=True)
    settings.app.cache_dir.mkdir(parents=True, exist_ok=True)
    settings.app.temp_dir.mkdir(parents=True, exist_ok=True)
    settings.app.logs_dir.mkdir(parents=True, exist_ok=True)

    configure_logging()
    await run_async_upgrade()
    await job_runtime.start()
    yield
    await job_runtime.stop()
    await sessionmanager.close()


settings = get_settings()
app = FastAPI(title=settings.app.project_name, lifespan=lifespan)
logger = logging.getLogger(__name__)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.app.cors_allow_origins,
    allow_origin_regex=settings.app.cors_allow_origin_regex,
    allow_methods=settings.app.cors_allow_methods,
    allow_headers=settings.app.cors_allow_headers,
    allow_credentials=settings.app.cors_allow_credentials,
)

_SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Permissions-Policy": "geolocation=(), microphone=()",
}

KO_READER_AUTH_EXEMPT_PATHS = {
    "/healthcheck",
    "/users/create",
    "/users/auth",
    "/syncs/progress",
    "/api/v1/app-auth/session",
    "/api/v1/app-auth/login",
    "/api/v1/app-auth/logout",
}


@app.middleware("http")
async def add_security_headers(request: Request, call_next: Callable) -> Response:
    started = time.perf_counter()
    try:
        path = request.url.path
        skip_global_auth = path == "/health" or path in KO_READER_AUTH_EXEMPT_PATHS or path.startswith("/syncs/progress/")
        if not skip_global_auth:
            is_frontend_request = not (
                path.startswith("/api/")
                or path.startswith("/opds")
                or path.startswith("/users/")
                or path == "/users/auth"
                or path == "/users/create"
                or path.startswith("/syncs/")
                or path == "/healthcheck"
            )
            if not is_frontend_request:
                ensure_request_authorized(request, challenge=path.startswith("/opds"))
        response = await call_next(request)
    except HTTPException as exc:
        response = JSONResponse(status_code=exc.status_code, content={"detail": exc.detail}, headers=exc.headers or {})
    for header, value in _SECURITY_HEADERS.items():
        response.headers[header] = value
    elapsed_ms = (time.perf_counter() - started) * 1000
    logger.info(
        "%s %s -> %s %.1fms",
        request.method,
        request.url.path,
        response.status_code,
        elapsed_ms,
    )
    if is_auth_enabled():
        response.headers["Cache-Control"] = "private, no-store"
    return response


app.include_router(system_router)
app.include_router(koreader_router)
app.include_router(koreader_app_router)
app.include_router(artifacts_router)
app.include_router(jobs_router)
app.include_router(library_router)
app.include_router(opds_router)
app.include_router(source_auth_router)
app.include_router(tracking_router)


frontend_dist_dir = settings.app.frontend_dist_dir
frontend_assets_dir = frontend_dist_dir / "assets"
if frontend_assets_dir.is_dir():
    app.mount("/assets", StaticFiles(directory=frontend_assets_dir), name="frontend-assets")


@app.get("/", include_in_schema=False)
async def serve_frontend_index() -> FileResponse:
    index_file = frontend_dist_dir / "index.html"
    if not index_file.is_file():
        raise HTTPException(status_code=404, detail="Frontend build not found")
    return FileResponse(index_file)


@app.get("/{full_path:path}", include_in_schema=False)
async def serve_frontend_path(full_path: str) -> FileResponse:
    if full_path.startswith("api/") or full_path.startswith("opds") or full_path == "health":
        raise HTTPException(status_code=404, detail="Not found")

    candidate = frontend_dist_dir / full_path
    if candidate.is_file():
        return FileResponse(candidate)

    index_file = frontend_dist_dir / "index.html"
    if not index_file.is_file():
        raise HTTPException(status_code=404, detail="Frontend build not found")
    return FileResponse(index_file)


if __name__ == "__main__":
    uvicorn.run(
        app="app.main:app",
        host=settings.server.host,
        port=settings.server.port,
        access_log=False,
    )
