FROM node:22-bookworm-slim AS web-build

WORKDIR /build/web
COPY web/package*.json ./
RUN npm ci
COPY web/ ./
RUN npm run build


FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    RANOBARR__APP__DATA_DIR=/data \
    RANOBARR__APP__FRONTEND_DIR=/app/web \
    RANOBARR__SERVER__HOST=0.0.0.0 \
    RANOBARR__SERVER__PORT=3030

WORKDIR /app

COPY server/ /app/server/
RUN uv sync --project /app/server --frozen --no-dev

COPY web/public/ /app/web/public/
COPY --from=web-build /build/web/dist /app/web/dist

RUN useradd --create-home --shell /usr/sbin/nologin ranobarr \
    && mkdir -p /data \
    && chown -R ranobarr:ranobarr /app /data

USER ranobarr

EXPOSE 3030

CMD ["uv", "run", "--project", "/app/server", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "3030", "--no-access-log"]
