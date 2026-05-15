import mimetypes
from pathlib import Path
from urllib.parse import urlparse


def resolve_asset_url(url: str) -> str:
    if url.startswith("//"):
        return f"https:{url}"
    if url.startswith("/"):
        return f"https://ranobelib.me{url}"
    return url


def asset_filename_from_url(url: str) -> str:
    path = urlparse(url).path
    name = Path(path).name
    return name or "asset.bin"


def guess_extension(media_type: str, fallback_name: str) -> str:
    suffix = Path(fallback_name).suffix
    if suffix:
        return suffix
    guessed = mimetypes.guess_extension(media_type)
    return guessed or ".bin"
