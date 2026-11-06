# Silsila API. Build from the repository root:
#   docker build -f backend/Dockerfile -t silsila-api .
FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:0.13.1 /uv /usr/local/bin/uv
ENV UV_LINK_MODE=copy UV_COMPILE_BYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app/backend
COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY backend/src ./src
RUN uv sync --frozen --no-dev
COPY data /app/data
COPY docs/evidence/*.json /app/docs/evidence/
# Demo mode: the database is recreated with the fictional families on every start.
ENV SILSILA_DEMO=1
EXPOSE 8000
CMD ["sh", "-c", "uv run --no-sync python -m silsila.api.seed && uv run --no-sync uvicorn silsila.api.app:app --host 0.0.0.0 --port 8000"]
