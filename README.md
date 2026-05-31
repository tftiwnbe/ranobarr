# Ranobarr

Ranobarr is a self-hosted RanobeLib tracker that keeps EPUB files current and exposes them through a reader-friendly OPDS catalog.

## What it does

- tracks RanobeLib titles
- keeps chapter snapshots and cached content on disk
- builds EPUB artifacts automatically
- exposes OPDS feeds for:
  - all books
  - recently updated
  - favorites
  - collections
  - genres
  - tags
- supports optional HTTP Basic auth across the web UI, API, and OPDS
- stores everything locally in SQLite and `/data`

## Quick start

Copy the example environment file and adjust the password:

```bash
cp .env.example .env
```

Start the app:

```bash
docker compose up -d --build
```

Open:

- Web UI: `http://localhost:3030`
- OPDS root: `http://localhost:3030/opds`

If auth is enabled, your reader and browser should use the same Basic auth credentials from `.env`.

## Optional KOReader Sync sidecar

Ranobarr does not reimplement the KOReader sync protocol. The reliable way to support KOReader progress sync is to run the official sync server beside it.

Start it only when you need it:

```bash
docker compose --profile koreader-sync up -d
```

Default KOReader Sync endpoint:

- `https://localhost:7200`

The official KOReader sync server ships with its own HTTPS listener and self-signed certificate, and documents Docker and Compose-based self-hosting directly in its repository. Sources:
- [koreader/koreader-sync-server](https://github.com/koreader/koreader-sync-server)

## Data and logs

- SQLite database: `/data/ranobarr.db`
- built artifacts: `/data/artifacts`
- cached chapter and cover assets: `/data/cache`
- rotating app log: `/data/logs/ranobarr.log`

## Configuration

Important environment variables:

- `RANOBARR_AUTH_ENABLED`
- `RANOBARR_AUTH_USERNAME`
- `RANOBARR_AUTH_PASSWORD`
- `RANOBARR_SCAN_INTERVAL_SECONDS`
- `RANOBARR_PORT`

## Development

Frontend:

```bash
npm --prefix web ci
npm --prefix web run build
```

Backend:

```bash
uv sync --project server --group dev
uv run --project server pytest
uv run --project server uvicorn app.main:app --app-dir server --reload --host 127.0.0.1 --port 3030
```

## CI/CD

- `CI` runs the frontend build and backend tests on pushes to `main` and on pull requests.
- `Release Image` publishes `ghcr.io/<owner>/<repo>` on pushed git tags matching `v*`.

## References

Ranobarr was informed by these public projects:

- [ivanvit100/DownloadLib](https://github.com/ivanvit100/DownloadLib)
- [zeroma25/ranobelib-downloader](https://github.com/zeroma25/ranobelib-downloader)
- [DustGalaxy/Ranobe2ebook](https://github.com/DustGalaxy/Ranobe2ebook)
- [ryadik/ranobelib-parser](https://github.com/ryadik/ranobelib-parser)
- [koreader/koreader-sync-server](https://github.com/koreader/koreader-sync-server)
