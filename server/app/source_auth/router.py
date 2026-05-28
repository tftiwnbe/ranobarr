from fastapi import APIRouter, Depends, Response, status
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.database import get_database_session
from .schemas import RanobeLibCredentialUpsert, RanobeLibCredentialValidation, RanobeLibCredentialView
from .service import (
    credential_view,
    delete_ranobelib_credential,
    get_ranobelib_credential,
    upsert_ranobelib_credential,
    validate_ranobelib_credential,
)

router = APIRouter(prefix="/api/v1/source-auth", tags=["source-auth"])


@router.get("/ranobelib", response_model=RanobeLibCredentialView | None)
async def get_source_credential(
    session: AsyncSession = Depends(get_database_session),
) -> RanobeLibCredentialView | None:
    return credential_view(await get_ranobelib_credential(session))


@router.put("/ranobelib", response_model=RanobeLibCredentialView)
async def put_source_credential(
    payload: RanobeLibCredentialUpsert,
    session: AsyncSession = Depends(get_database_session),
) -> RanobeLibCredentialView:
    credential = await upsert_ranobelib_credential(session, payload)
    return credential_view(credential)  # type: ignore[return-value]


@router.delete("/ranobelib", status_code=status.HTTP_204_NO_CONTENT)
async def delete_source_credential(
    session: AsyncSession = Depends(get_database_session),
) -> Response:
    await delete_ranobelib_credential(session)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/ranobelib/validate", response_model=RanobeLibCredentialValidation)
async def validate_source_credential(
    session: AsyncSession = Depends(get_database_session),
) -> RanobeLibCredentialValidation:
    return await validate_ranobelib_credential(session)
