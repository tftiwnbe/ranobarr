import httpx

from app.builds.assets import collect_asset_urls, ensure_binary_assets_cached


def test_collect_asset_urls_deduplicates_and_resolves_cover() -> None:
    urls = collect_asset_urls(
        [
            '<p><img src="/a.jpg" /></p>',
            '<p><img src="//cdn.example.com/b.jpg" /></p>',
            '<p><img src="/a.jpg" /></p>',
        ],
        cover_url="/cover.jpg",
    )
    assert urls == [
        "https://ranobelib.me/cover.jpg",
        "https://ranobelib.me/a.jpg",
        "https://cdn.example.com/b.jpg",
    ]


async def test_ensure_binary_assets_cached_reuses_existing_files(db, temp_data_dir, monkeypatch) -> None:
    calls = {"count": 0}

    async def fake_fetch_binary_asset(client: httpx.AsyncClient, url: str):
        calls["count"] += 1
        return ("image.jpg", b"binary-data", "image/jpeg")

    monkeypatch.setattr("app.builds.assets.fetch_binary_asset", fake_fetch_binary_asset)

    urls = ["https://ranobelib.me/a.jpg"]
    first = await ensure_binary_assets_cached(db, urls)
    second = await ensure_binary_assets_cached(db, urls)

    assert calls["count"] == 1
    assert first["https://ranobelib.me/a.jpg"].relative_path == second["https://ranobelib.me/a.jpg"].relative_path
    assert (temp_data_dir / first["https://ranobelib.me/a.jpg"].relative_path).is_file()
