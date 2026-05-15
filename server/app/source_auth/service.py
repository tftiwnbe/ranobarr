from __future__ import annotations

from datetime import datetime, timezone

import httpx
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models import SourceCredential
from app.ranobelib import RanobeLibClient
from .schemas import RanobeLibCredentialUpsert, RanobeLibCredentialView


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


async def get_ranobelib_credential(session: AsyncSession) -> SourceCredential | None:
    result = await session.exec(select(SourceCredential).where(SourceCredential.provider == "ranobelib"))
    return result.one_or_none()


async def upsert_ranobelib_credential(
    session: AsyncSession, payload: RanobeLibCredentialUpsert
) -> SourceCredential:
    credential = await get_ranobelib_credential(session)
    if credential is None:
        credential = SourceCredential(provider="ranobelib")

    credential.access_token = payload.access_token
    credential.refresh_token = payload.refresh_token
    credential.expires_at = payload.expires_at
    credential.updated_at = utcnow()
    session.add(credential)
    await session.commit()
    await session.refresh(credential)
    return credential


async def delete_ranobelib_credential(session: AsyncSession) -> bool:
    credential = await get_ranobelib_credential(session)
    if credential is None:
        return False
    await session.delete(credential)
    await session.commit()
    return True


def credential_view(credential: SourceCredential | None) -> RanobeLibCredentialView | None:
    if credential is None:
        return None
    return RanobeLibCredentialView(
        provider=credential.provider,
        has_access_token=bool(credential.access_token),
        has_refresh_token=bool(credential.refresh_token),
        expires_at=credential.expires_at,
        updated_at=credential.updated_at,
    )


async def make_ranobelib_client(session: AsyncSession) -> RanobeLibClient:
    client = RanobeLibClient()
    credential = await get_ranobelib_credential(session)
    if credential and credential.access_token:
        client.set_token(credential.access_token)
        if credential.refresh_token:
            client.set_token_refresh_callback(lambda: refresh_ranobelib_token(session, client))
    return client


async def refresh_ranobelib_token(session: AsyncSession, client: RanobeLibClient) -> bool:
    credential = await get_ranobelib_credential(session)
    if credential is None or not credential.refresh_token:
        return False

    token_url = "https://api.cdnlibs.org/api/auth/oauth/token"
    payload = {
        "grant_type": "refresh_token",
        "client_id": 1,
        "refresh_token": credential.refresh_token,
    }
    async with httpx.AsyncClient(timeout=15) as refresh_client:
        response = await refresh_client.post(token_url, json=payload, headers=client.base_headers)
    if response.status_code == 400:
        return False
    response.raise_for_status()
    token_data = response.json()
    access_token = token_data.get("access_token")
    if not access_token:
        return False

    credential.access_token = access_token
    credential.refresh_token = token_data.get("refresh_token", credential.refresh_token)
    credential.updated_at = utcnow()
    client.set_token(access_token)
    session.add(credential)
    await session.commit()
    return True
