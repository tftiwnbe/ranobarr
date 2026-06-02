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
- implements a KOReader-compatible progress sync server directly in the app
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

## KOReader sync

Ranobarr now exposes KOReader-compatible sync endpoints directly, so devices like the Xteink X4 can push and pull reading progress over HTTP(S).

There is no separate `kosync` sidecar anymore. Point KOReader at the Ranobarr app itself.

In the web app:

- open `koreader sync`
- point KOReader or CrossPoint at this app as the custom sync server
- create or log into the same KOReader sync account on the device
- refresh the drawer to inspect synced documents and label unknown hashes

Ranobarr accepts the official KOReader sync protocol routes:

- `POST /users/create`
- `GET /users/auth`
- `PUT /syncs/progress`
- `GET /syncs/progress/:document`
- `GET /healthcheck`

Current behavior:

- stores KOReader sync users and per-document progress in SQLite
- automatically links synced documents to tracked Ranobarr titles when the KOReader document hash matches a built EPUB artifact
- lets you assign a title/author and optionally link unknown synced document hashes in the app UI
- still cannot infer a sideloaded title automatically from the KOReader sync protocol alone, because the protocol sends a document hash and progress metadata, not filenames or book titles

If app-wide Basic auth is enabled, the normal web UI and `/api/*` routes still use it. The KOReader protocol routes use KOReader’s own `x-auth-user` / `x-auth-key` authentication flow for compatibility with devices.

## Data and logs

- SQLite database: `/data/ranobarr.db`
- built artifacts: `/data/artifacts`
- cached chapter and cover assets: `/data/cache`
- rotating app log: `/data/logs/ranobarr.log`

## Configuration

Important environment variables:

- `RANOBARR__AUTH__ENABLED`
- `RANOBARR__AUTH__USERNAME`
- `RANOBARR__AUTH__PASSWORD`
- `RANOBARR__SCHEDULER__SCAN_INTERVAL_SECONDS`
- `RANOBARR__SERVER__PORT`

If you use `docker compose`, the compose file maps shell variables like `RANOBARR_AUTH_ENABLED` into the nested app variables above.

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
