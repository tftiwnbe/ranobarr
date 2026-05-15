from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.config import get_settings


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def cache_file_path(relative_path: str) -> Path:
    return get_settings().app.data_dir / relative_path


def artifact_file_path(relative_path: str) -> Path:
    return get_settings().app.data_dir / relative_path


def asset_file_path(relative_path: str) -> Path:
    return get_settings().app.data_dir / relative_path


def write_chapter_cache(book_id: str, chapter_key: str, payload: dict[str, Any]) -> str:
    settings = get_settings()
    chapter_dir = settings.app.cache_dir / "chapters" / book_id
    chapter_dir.mkdir(parents=True, exist_ok=True)
    file_path = chapter_dir / f"{chapter_key}.json"
    file_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return str(file_path.relative_to(settings.app.data_dir))


def write_artifact_manifest(book_id: str, payload: dict[str, Any]) -> str:
    settings = get_settings()
    artifact_dir = settings.app.artifacts_dir / book_id
    artifact_dir.mkdir(parents=True, exist_ok=True)
    filename = f"manifest-{utcnow().strftime('%Y%m%d%H%M%S%f')}.json"
    file_path = artifact_dir / filename
    file_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return str(file_path.relative_to(settings.app.data_dir))


def write_epub_artifact(book_id: str, content: bytes) -> str:
    settings = get_settings()
    artifact_dir = settings.app.artifacts_dir / book_id
    artifact_dir.mkdir(parents=True, exist_ok=True)
    filename = f"book-{utcnow().strftime('%Y%m%d%H%M%S%f')}.epub"
    file_path = artifact_dir / filename
    file_path.write_bytes(content)
    return str(file_path.relative_to(settings.app.data_dir))


def write_binary_asset(original_name: str, content_hash: str, content: bytes) -> str:
    settings = get_settings()
    ext = Path(original_name).suffix or ".bin"
    assets_dir = settings.app.cache_dir / "assets"
    assets_dir.mkdir(parents=True, exist_ok=True)
    file_path = assets_dir / f"{content_hash}{ext}"
    if not file_path.exists():
        file_path.write_bytes(content)
    return str(file_path.relative_to(settings.app.data_dir))
