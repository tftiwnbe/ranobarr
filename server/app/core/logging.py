from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

from app.config import get_settings


def configure_logging() -> None:
    settings = get_settings()
    log_dir = settings.app.logs_dir
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "ranobarr.log"

    root_logger = logging.getLogger()
    if any(isinstance(handler, RotatingFileHandler) and handler.baseFilename == str(log_file) for handler in root_logger.handlers):
        return

    formatter = logging.Formatter(
        fmt="%(asctime)s %(levelname)s [%(name)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    file_handler = RotatingFileHandler(
        filename=log_file,
        maxBytes=2_000_000,
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    file_handler.setLevel(logging.INFO)

    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)
    stream_handler.setLevel(logging.INFO)

    root_logger.setLevel(logging.INFO)
    root_logger.addHandler(file_handler)
    if not any(type(handler) is logging.StreamHandler for handler in root_logger.handlers):
        root_logger.addHandler(stream_handler)

    logging.getLogger("httpx").setLevel(logging.WARNING)
