import uvicorn
from contextlib import asynccontextmanager
from typing import Callable

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.artifacts.router import router as artifacts_router
from app.config import get_settings
from app.core.database import run_async_upgrade, sessionmanager
from app.core.jobs import job_runtime
from app.jobs.router import router as jobs_router
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

    await run_async_upgrade()
    await job_runtime.start()
    yield
    await job_runtime.stop()
    await sessionmanager.close()


settings = get_settings()
app = FastAPI(title=settings.app.project_name, lifespan=lifespan)

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


@app.middleware("http")
async def add_security_headers(request: Request, call_next: Callable) -> Response:
    response = await call_next(request)
    for header, value in _SECURITY_HEADERS.items():
        response.headers[header] = value
    return response


app.include_router(system_router)
app.include_router(artifacts_router)
app.include_router(jobs_router)
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
    )
