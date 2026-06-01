from datetime import datetime

from pydantic import BaseModel, Field


class KOReaderDocumentUpdateRequest(BaseModel):
    title: str | None = Field(default=None, max_length=240)
    author: str | None = Field(default=None, max_length=240)
    linked_book_id: str | None = None


class KOReaderDocumentSummary(BaseModel):
    id: str
    username: str
    document_hash: str
    title: str | None
    author: str | None
    linked_book_id: str | None
    linked_book_title: str | None
    progress: str | None
    progress_percent: float | None
    device: str | None
    device_id: str | None
    progress_timestamp: int | None
    updated_at: datetime
    created_at: datetime


class KOReaderStateResponse(BaseModel):
    documents: list[KOReaderDocumentSummary]


class KOReaderProtocolRegisterRequest(BaseModel):
    username: str
    password: str


class KOReaderProtocolRegisterResponse(BaseModel):
    username: str


class KOReaderProtocolAuthResponse(BaseModel):
    authorized: str


class KOReaderProtocolProgressUpdateRequest(BaseModel):
    document: str
    progress: str
    percentage: float
    device: str
    device_id: str | None = None


class KOReaderProtocolProgressWriteResponse(BaseModel):
    document: str
    timestamp: int


class KOReaderProtocolProgressReadResponse(BaseModel):
    document: str | None = None
    percentage: float | None = None
    progress: str | None = None
    device: str | None = None
    device_id: str | None = None
    timestamp: int | None = None


class KOReaderProtocolHealthResponse(BaseModel):
    state: str
