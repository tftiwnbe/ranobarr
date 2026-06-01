from fastapi import APIRouter, Depends, Header, HTTPException, status
from fastapi.responses import JSONResponse
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.database import get_database_session
from app.core.errors import TrackingError
from .schemas import (
    KOReaderDocumentUpdateRequest,
    KOReaderProtocolAuthResponse,
    KOReaderProtocolHealthResponse,
    KOReaderProtocolProgressUpdateRequest,
    KOReaderProtocolRegisterRequest,
    KOReaderProtocolRegisterResponse,
    KOReaderStateResponse,
)
from .service import (
    ERROR_INVALID_FIELDS,
    ERROR_UNAUTHORIZED,
    ProtocolError,
    authorize_sync_user,
    build_koreader_state,
    get_document_progress,
    register_sync_user,
    update_document_progress,
    update_koreader_document,
)

router = APIRouter(tags=["koreader"])

app_router = APIRouter(prefix="/api/v1/koreader", tags=["koreader"])


def _protocol_error_response(exc: ProtocolError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={"code": exc.code, "message": exc.message},
    )


@app_router.get("", response_model=KOReaderStateResponse)
async def get_koreader_state(
    session: AsyncSession = Depends(get_database_session),
) -> KOReaderStateResponse:
    return await build_koreader_state(session)


@app_router.patch("/documents/{document_id}", response_model=KOReaderStateResponse)
async def patch_koreader_document(
    document_id: str,
    request: KOReaderDocumentUpdateRequest,
    session: AsyncSession = Depends(get_database_session),
) -> KOReaderStateResponse:
    try:
        return await update_koreader_document(session, document_id=document_id, request=request)
    except TrackingError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.get("/healthcheck", response_model=KOReaderProtocolHealthResponse)
async def koreader_healthcheck() -> KOReaderProtocolHealthResponse:
    return KOReaderProtocolHealthResponse(state="OK")


@router.post("/users/create", response_model=KOReaderProtocolRegisterResponse, status_code=status.HTTP_201_CREATED)
async def koreader_register_user(
    request: KOReaderProtocolRegisterRequest,
    session: AsyncSession = Depends(get_database_session),
):
    try:
        user = await register_sync_user(session, request.username, request.password)
        return KOReaderProtocolRegisterResponse(username=user.username)
    except ProtocolError as exc:
        return _protocol_error_response(exc)


@router.get("/users/auth", response_model=KOReaderProtocolAuthResponse)
async def koreader_auth_user(
    x_auth_user: str | None = Header(default=None),
    x_auth_key: str | None = Header(default=None),
    session: AsyncSession = Depends(get_database_session),
):
    try:
        await authorize_sync_user(session, username=x_auth_user, auth_key=x_auth_key)
        return KOReaderProtocolAuthResponse(authorized="OK")
    except ProtocolError as exc:
        return _protocol_error_response(exc)


@router.get("/syncs/progress/{document}", response_model_exclude_none=True)
async def koreader_get_progress(
    document: str,
    x_auth_user: str | None = Header(default=None),
    x_auth_key: str | None = Header(default=None),
    session: AsyncSession = Depends(get_database_session),
):
    try:
        user = await authorize_sync_user(session, username=x_auth_user, auth_key=x_auth_key)
        return await get_document_progress(session, user=user, document_hash=document)
    except ProtocolError as exc:
        return _protocol_error_response(exc)


@router.put("/syncs/progress")
async def koreader_update_progress(
    request: KOReaderProtocolProgressUpdateRequest,
    x_auth_user: str | None = Header(default=None),
    x_auth_key: str | None = Header(default=None),
    session: AsyncSession = Depends(get_database_session),
):
    try:
        user = await authorize_sync_user(session, username=x_auth_user, auth_key=x_auth_key)
        document, timestamp = await update_document_progress(
            session,
            user=user,
            document_hash=request.document,
            progress=request.progress,
            percentage=request.percentage,
            device=request.device,
            device_id=request.device_id,
        )
        return {"document": document, "timestamp": timestamp}
    except ProtocolError as exc:
        return _protocol_error_response(exc)
