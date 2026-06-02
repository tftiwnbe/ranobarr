from __future__ import annotations

import hashlib
import logging
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.artifacts.service import koreader_sync_filename, latest_artifacts_for_books
from app.builds.storage import artifact_file_path
from app.config import get_settings
from app.core.errors import TrackingError
from app.core.security import is_auth_enabled
from app.core.titles import normalize_book_title
from app.models import Artifact, Book, KOReaderSyncDocument, KOReaderSyncUser
from .schemas import (
    KOReaderDocumentSummary,
    KOReaderDocumentUpdateRequest,
    KOReaderProtocolProgressReadResponse,
    KOReaderStateResponse,
)

logger = logging.getLogger(__name__)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def current_timestamp() -> int:
    return int(datetime.now(timezone.utc).timestamp())


@dataclass(slots=True)
class ProtocolError(Exception):
    code: int
    message: str
    status_code: int


ERROR_UNAUTHORIZED = ProtocolError(code=2001, message="Unauthorized", status_code=401)
ERROR_USER_EXISTS = ProtocolError(code=2002, message="Username is already registered.", status_code=402)
ERROR_INVALID_FIELDS = ProtocolError(code=2003, message="Invalid username and/or password field.", status_code=400)
ERROR_DOCUMENT_MISSING = ProtocolError(code=2004, message="Field 'document' not provided.", status_code=403)


def is_valid_field(field: str | None) -> bool:
    return isinstance(field, str) and len(field) > 0


def is_valid_key_field(field: str | None) -> bool:
    return is_valid_field(field) and ":" not in str(field)


def canonicalize_title(value: str) -> str:
    normalized = normalize_book_title(value).casefold()
    return re.sub(r"[^a-z0-9\u0400-\u04ff]+", "", normalized)


async def _find_user_by_username(session: AsyncSession, username: str) -> KOReaderSyncUser | None:
    result = await session.exec(select(KOReaderSyncUser).where(KOReaderSyncUser.username == username))
    return result.one_or_none()


async def register_sync_user(session: AsyncSession, username: str, auth_key: str) -> KOReaderSyncUser:
    if not is_valid_key_field(username) or not is_valid_field(auth_key):
        raise ERROR_INVALID_FIELDS
    existing = await _find_user_by_username(session, username)
    if existing is not None:
        raise ERROR_USER_EXISTS
    user = KOReaderSyncUser(username=username, auth_key=auth_key)
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


def _app_auth_matches(username: str, auth_key: str) -> bool:
    if not is_auth_enabled():
        return False
    settings = get_settings()
    if settings.auth.username != username:
        return False
    raw_password = settings.auth.password
    md5_password = hashlib.md5(raw_password.encode("utf-8")).hexdigest()
    return auth_key == raw_password or auth_key == md5_password


async def _ensure_sync_user_for_app_auth(session: AsyncSession, username: str, auth_key: str) -> KOReaderSyncUser:
    user = await _find_user_by_username(session, username)
    now = utcnow()
    if user is None:
        user = KOReaderSyncUser(username=username, auth_key=auth_key, created_at=now, updated_at=now)
    else:
        user.auth_key = auth_key
        user.updated_at = now
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


async def authorize_sync_user(
    session: AsyncSession,
    *,
    username: str | None,
    auth_key: str | None,
) -> KOReaderSyncUser:
    logger.info(
        "KOReader auth attempt user_present=%s key_present=%s username=%s",
        bool(username),
        bool(auth_key),
        username or "",
    )
    if not is_valid_key_field(username) or not is_valid_field(auth_key):
        logger.warning("KOReader auth rejected: missing or invalid auth headers")
        raise ERROR_UNAUTHORIZED
    user = await _find_user_by_username(session, str(username))
    if user is not None and user.auth_key == auth_key:
        logger.info("KOReader auth accepted using stored sync user username=%s", username)
        return user
    if _app_auth_matches(str(username), str(auth_key)):
        logger.info("KOReader auth accepted using app auth bridge username=%s", username)
        return await _ensure_sync_user_for_app_auth(session, str(username), str(auth_key))
    logger.warning(
        "KOReader auth rejected: user_found=%s app_auth_enabled=%s username=%s",
        user is not None,
        is_auth_enabled(),
        username,
    )
    raise ERROR_UNAUTHORIZED


async def _find_document(session: AsyncSession, *, user_id: str, document_hash: str) -> KOReaderSyncDocument | None:
    result = await session.exec(
        select(KOReaderSyncDocument).where(
            KOReaderSyncDocument.user_id == user_id,
            KOReaderSyncDocument.document_hash == document_hash,
        )
    )
    return result.one_or_none()


def artifact_md5(relative_path: str) -> str | None:
    file_path = artifact_file_path(relative_path)
    if not file_path.is_file():
        return None
    digest = hashlib.md5()
    with file_path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def koreader_filename_md5(book: Book) -> str:
    return hashlib.md5(koreader_sync_filename(book).encode("utf-8")).hexdigest()


async def find_linked_book_id_for_document(session: AsyncSession, document_hash: str) -> str | None:
    books_result = await session.exec(select(Book))
    books = books_result.all()
    book_ids = [book.id for book in books]
    latest_epubs = await latest_artifacts_for_books(session, book_ids=book_ids, format_name="epub")
    for book_id, artifact in latest_epubs.items():
        digest = artifact_md5(artifact.relative_path)
        if digest == document_hash:
            return book_id
    for book in books:
        if koreader_filename_md5(book) == document_hash:
            return book.id
    return None


async def update_document_progress(
    session: AsyncSession,
    *,
    user: KOReaderSyncUser,
    document_hash: str,
    progress: str,
    percentage: float,
    device: str,
    device_id: str | None,
) -> tuple[str, int]:
    if not is_valid_key_field(document_hash):
        raise ERROR_DOCUMENT_MISSING
    if not isinstance(percentage, (int, float)) or not is_valid_field(progress) or not is_valid_field(device):
        raise ERROR_INVALID_FIELDS

    document = await _find_document(session, user_id=user.id, document_hash=document_hash)
    timestamp = current_timestamp()
    if document is None:
        document = KOReaderSyncDocument(
            user_id=user.id,
            document_hash=document_hash,
            linked_book_id=await find_linked_book_id_for_document(session, document_hash),
        )
    document.progress = progress
    document.progress_percent = float(percentage)
    document.device = device
    document.device_id = device_id
    document.progress_timestamp = timestamp
    document.updated_at = utcnow()
    session.add(document)
    await session.commit()
    return document_hash, timestamp


async def get_document_progress(
    session: AsyncSession,
    *,
    user: KOReaderSyncUser,
    document_hash: str,
) -> KOReaderProtocolProgressReadResponse | dict[str, object]:
    if not is_valid_key_field(document_hash):
        raise ERROR_DOCUMENT_MISSING
    document = await _find_document(session, user_id=user.id, document_hash=document_hash)
    if document is None:
        return {}
    return KOReaderProtocolProgressReadResponse(
        document=document.document_hash,
        percentage=document.progress_percent,
        progress=document.progress,
        device=document.device,
        device_id=document.device_id,
        timestamp=document.progress_timestamp,
    )


def _display_title(document: KOReaderSyncDocument) -> str | None:
    if document.title:
        return normalize_book_title(document.title)
    return None


async def build_koreader_state(session: AsyncSession) -> KOReaderStateResponse:
    docs_result = await session.exec(
        select(KOReaderSyncDocument, KOReaderSyncUser)
        .join(KOReaderSyncUser, KOReaderSyncUser.id == KOReaderSyncDocument.user_id)
        .order_by(KOReaderSyncDocument.updated_at.desc())
    )
    rows = docs_result.all()

    linked_ids = [doc.linked_book_id for doc, _user in rows if doc.linked_book_id]
    linked_titles: dict[str, str] = {}
    if linked_ids:
        linked_books = await session.exec(select(Book).where(Book.id.in_(linked_ids)))
        linked_titles = {book.id: normalize_book_title(book.title) for book in linked_books.all()}

    documents = [
        KOReaderDocumentSummary(
            id=document.id,
            username=user.username,
            document_hash=document.document_hash,
            title=_display_title(document),
            author=document.author,
            linked_book_id=document.linked_book_id,
            linked_book_title=linked_titles.get(document.linked_book_id) if document.linked_book_id else None,
            progress=document.progress,
            progress_percent=document.progress_percent,
            device=document.device,
            device_id=document.device_id,
            progress_timestamp=document.progress_timestamp,
            updated_at=document.updated_at,
            created_at=document.created_at,
        )
        for document, user in rows
    ]
    return KOReaderStateResponse(documents=documents)


async def update_koreader_document(
    session: AsyncSession,
    *,
    document_id: str,
    request: KOReaderDocumentUpdateRequest,
) -> KOReaderStateResponse:
    document = await session.get(KOReaderSyncDocument, document_id)
    if document is None:
        raise TrackingError("KOReader document not found")

    fields_set = getattr(request, "model_fields_set", set())
    linked_book: Book | None = None

    if "linked_book_id" in fields_set:
        if request.linked_book_id:
            linked_book = await session.get(Book, request.linked_book_id)
            if linked_book is None:
                raise TrackingError("Tracked book not found")
            document.linked_book_id = linked_book.id
        else:
            document.linked_book_id = None

    if "title" in fields_set:
        normalized = normalize_book_title(request.title) if request.title and request.title.strip() else None
        if normalized is not None:
            document.title = normalized
        elif linked_book is not None:
            document.title = normalize_book_title(linked_book.title)
        else:
            document.title = None
    elif linked_book is not None and not document.title:
        document.title = normalize_book_title(linked_book.title)

    if "author" in fields_set:
        author = request.author.strip() if request.author else ""
        if author:
            document.author = author
        elif linked_book is not None:
            document.author = linked_book.author
        else:
            document.author = None
    elif linked_book is not None and not document.author:
        document.author = linked_book.author

    document.updated_at = utcnow()
    session.add(document)
    await session.commit()
    return await build_koreader_state(session)
