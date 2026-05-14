import asyncio
import time
from collections import deque
from typing import Any
from urllib.parse import urlparse

import httpx


REQUESTS_LIMIT = 90
REQUESTS_PERIOD = 60
REQUEST_TIMEOUT = 20
RETRY_DELAYS = [1, 3, 10, 30]


class RanobeLibError(RuntimeError):
    pass


class RanobeLibClient:
    def __init__(self) -> None:
        self.api_url = "https://api.cdnlibs.org/api/manga"
        self.site_url = "https://ranobelib.me"
        self._request_timestamps: deque[float] = deque()
        self._rate_lock = asyncio.Lock()
        self._client = httpx.AsyncClient(
            timeout=REQUEST_TIMEOUT,
            headers={
                "User-Agent": "Mozilla/5.0",
                "Origin": self.site_url,
                "Referer": f"{self.site_url}/",
                "Site-Id": "3",
            },
        )

    async def close(self) -> None:
        await self._client.aclose()

    @staticmethod
    def extract_slug_from_url(url: str) -> str | None:
        parsed_url = urlparse(url)
        path_parts = parsed_url.path.strip("/").split("/")
        if len(path_parts) >= 3 and path_parts[0] == "ru" and path_parts[1] == "book":
            return path_parts[2]
        return None

    async def get_novel_info(self, slug: str) -> dict[str, Any]:
        fields = [
            "summary",
            "genres",
            "tags",
            "teams",
            "authors",
            "status_id",
            "artists",
            "format",
            "publisher",
            "chap_count",
            "releaseDate",
        ]
        params = [("fields[]", field) for field in fields]
        data = await self._get_json(f"{self.api_url}/{slug}", params=params)
        return data.get("data", {})

    async def get_novel_chapters(self, slug: str) -> list[dict[str, Any]]:
        data = await self._get_json(f"{self.api_url}/{slug}/chapters")
        chapters = data.get("data", [])
        filtered: list[dict[str, Any]] = []
        for chapter in chapters:
            branches = chapter.get("branches", [])
            is_on_moderation = any(
                isinstance(branch, dict) and branch.get("moderation", {}).get("id") == 0
                for branch in branches
            )
            if not is_on_moderation:
                filtered.append(chapter)
        return filtered

    async def get_chapter_content(
        self,
        slug: str,
        volume: str,
        number: str,
        branch_id: str | None = None,
    ) -> dict[str, Any]:
        params: dict[str, str] = {"volume": volume, "number": number}
        if branch_id:
            params["branch_id"] = branch_id
        data = await self._get_json(f"{self.api_url}/{slug}/chapter", params=params)
        return data.get("data", {})

    async def _get_json(self, url: str, params: Any = None) -> dict[str, Any]:
        last_error: Exception | None = None
        for attempt, delay in enumerate(RETRY_DELAYS, start=1):
            try:
                await self._wait_for_rate_limit()
                response = await self._client.get(url, params=params)
                if response.status_code >= 500:
                    raise RanobeLibError(f"RanobeLib server error {response.status_code}")
                if response.status_code == 404:
                    return {}
                response.raise_for_status()
                return response.json()
            except (httpx.HTTPError, ValueError, RanobeLibError) as exc:
                last_error = exc
                if attempt == len(RETRY_DELAYS):
                    break
                await asyncio.sleep(delay)
        raise RanobeLibError(f"Failed to fetch RanobeLib resource: {last_error}") from last_error

    async def _wait_for_rate_limit(self) -> None:
        async with self._rate_lock:
            current_time = time.monotonic()

            while self._request_timestamps and self._request_timestamps[0] < current_time - REQUESTS_PERIOD:
                self._request_timestamps.popleft()

            if len(self._request_timestamps) >= REQUESTS_LIMIT:
                wait_for_slot = self._request_timestamps[0] - (current_time - REQUESTS_PERIOD)
                if wait_for_slot > 0:
                    await asyncio.sleep(wait_for_slot)

                current_time = time.monotonic()
                while self._request_timestamps and self._request_timestamps[0] < current_time - REQUESTS_PERIOD:
                    self._request_timestamps.popleft()

            if self._request_timestamps:
                interval = REQUESTS_PERIOD / REQUESTS_LIMIT
                next_allowed_time = self._request_timestamps[-1] + interval
                wait_time = next_allowed_time - current_time
                if wait_time > 0:
                    await asyncio.sleep(wait_time)

            self._request_timestamps.append(time.monotonic())
