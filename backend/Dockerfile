# syntax=docker/dockerfile:1

FROM python:3.11-slim AS builder

# Build tools needed for compiled extensions (webrtcvad C extension)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build
COPY backend/requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

FROM python:3.11-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

WORKDIR /app

COPY --from=builder /install /usr/local

# ── Application code (PYTHONPATH=/app so 'import app.*' works) ──────────────
COPY backend/app ./app

# ── Full backend/ tree (for run_phase*.py which checks backend/app/... paths) ─
COPY backend/app    ./backend/app
COPY backend/tests  ./backend/tests
COPY backend/supabase ./backend/supabase
COPY backend/pytest.ini ./backend/pytest.ini

# ── Project-root files needed by _phase_common.py ────────────────────────────
COPY .env.example ./.env.example

# ── Phase verification scripts ────────────────────────────────────────────────
COPY scripts ./scripts

# ── pytest config at /app (for direct 'pytest' invocations) ──────────────────
COPY backend/pytest.ini ./pytest.ini

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
