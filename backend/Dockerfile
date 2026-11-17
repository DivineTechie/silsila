# Silsila API. Build from the repository root:
#   docker build -f backend/Dockerfile -t silsila-api .
FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:0.13.1 /uv /usr/local/bin/uv
ENV UV_LINK_MODE=copy UV_COMPILE_BYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app/backend
COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY backend/src ./src
# operators' check of the audit chain (python scripts/verify_audit.py)
COPY backend/scripts/verify_audit.py ./scripts/
RUN uv sync --frozen --no-dev
COPY data /app/data
COPY docs/evidence/*.json /app/docs/evidence/
# the guide reads the hazard log for one of its lookups
COPY docs/governance/hazard-log.md /app/docs/governance/
# Non-root user; /app/var holds the demo SQLite file (production uses Postgres via SILSILA_DATABASE_URL).
RUN useradd --system --uid 10001 --home /app silsila && mkdir -p /app/var && chown -R silsila /app/var
# run from the synced virtualenv directly (uv would need a writable cache)
ENV PATH=/app/backend/.venv/bin:$PATH SILSILA_DB=/app/var/silsila.db SILSILA_WORKERS=1
# Demo mode (default): the database is recreated with the fictional families on every start.
# Production: run with SILSILA_DEMO=0; it never seeds and refuses to start if misconfigured.
ENV SILSILA_DEMO=1
USER silsila
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD ["python", "-c", "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/live', timeout=4).status == 200 else 1)"]
CMD ["sh", "-c", "if [ \"$SILSILA_DEMO\" = \"1\" ]; then python -m silsila.api.seed; fi && exec uvicorn silsila.api.app:app --host 0.0.0.0 --port 8000 --workers \"${SILSILA_WORKERS:-1}\" --proxy-headers --forwarded-allow-ips='*' --no-access-log"]
