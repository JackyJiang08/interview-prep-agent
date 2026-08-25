# The whole system as one image: the built web app served by the API that
# drives the agent. It runs with zero environment variables — demo mode is
# keyless by design, and live mode lights up per session when a client
# supplies its own credentials.

# --- stage 1: build the web app -------------------------------------------
FROM node:22-slim AS web
WORKDIR /web
COPY web/package.json web/package-lock.json ./
RUN npm ci
COPY web/ ./
RUN npm run build

# --- stage 2: the runtime --------------------------------------------------
FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8000

WORKDIR /app

# Dependencies first, so a source change does not reinstall them.
COPY requirements.txt requirements-server.txt ./
RUN pip install --no-cache-dir -r requirements-server.txt

COPY pyproject.toml README.md LICENSE ./
COPY src/ ./src/
COPY examples/sample_job_description.txt examples/sample_evidence.yaml ./examples/
RUN pip install --no-cache-dir --no-deps .

# The built app, at the path the server mounts.
COPY --from=web /web/dist ./web/dist

# Run as a non-root user that owns nothing it does not need.
RUN useradd --create-home --uid 10001 appuser \
    && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000
CMD ["sh", "-c", "uvicorn --factory interview_prep_agent.server:create_app --host 0.0.0.0 --port ${PORT:-8000}"]
