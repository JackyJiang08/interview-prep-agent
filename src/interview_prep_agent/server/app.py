"""The web session layer: a thin, bounded wrapper over the agent.

Nothing here changes the graph, the workflow or the evaluation suite. A
session is one agent thread; its WebSocket forwards the run's own events and
feeds answers back into the same thread. Demo mode injects the fixture
provider the evaluation suite already uses; live mode builds a real provider
from a key that lives only in the session object.
"""

from __future__ import annotations

import asyncio
import json
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from ..config import Settings, load_settings
from ..providers import PROVIDERS, ProviderError
from .demo import demo_inputs, demo_provider, list_demos
from .driver import DISCONNECTED, start_run
from .sessions import SessionRefused, SessionStore

CLEANUP_INTERVAL_SECONDS = 60


class CreateSession(BaseModel):
    """The create-session request body."""

    mode: str = Field(pattern="^(demo|live)$")
    demo_id: str | None = None
    jd_text: str = ""
    evidence_text: str = ""
    evidence_format: str = Field(default="yaml", pattern="^(yaml|markdown)$")
    round_text: str = ""
    research_text: str = ""
    provider: str = Field(default="gemini", pattern="^(gemini|azure)$")
    gemini_api_key: str | None = None
    tavily_api_key: str | None = None
    azure_api_key: str | None = None
    azure_endpoint: str | None = None
    azure_deployment: str | None = None


def _refusal(status_code: int, category: str, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"error": {"category": category, "message": message}},
    )


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build the application with its store and cleanup task."""
    settings = settings or load_settings()
    store = SessionStore(
        max_concurrent_sessions=settings.max_concurrent_sessions,
        max_sessions_per_ip=settings.max_sessions_per_ip,
        session_ttl_seconds=settings.session_ttl_seconds,
    )

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        task = asyncio.create_task(_cleanup_loop(store))
        try:
            yield
        finally:
            task.cancel()

    app = FastAPI(title="interview-prep-agent", lifespan=lifespan)
    app.state.store = store
    app.state.settings = settings
    if settings.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origins,
            allow_methods=["GET", "POST"],
            allow_headers=["*"],
        )

    @app.exception_handler(SessionRefused)
    async def _refused(_request: Request, exc: SessionRefused) -> JSONResponse:
        return _refusal(exc.status_code, exc.category, exc.message)

    @app.get("/api/health")
    async def health() -> dict[str, Any]:
        """Liveness and capability probe.

        Demo mode is always available: it needs no credentials. Live mode is
        available per session, when the client supplies its own; the server
        holds no model keys of its own.
        """
        from .. import __version__

        return {
            "status": "ok",
            "version": __version__,
            "modes": {
                "demo": True,
                "live": {
                    "available_per_session": True,
                    "providers": list(PROVIDERS),
                    "server_side_credentials": False,
                },
            },
            "active_sessions": store.active_count(),
        }

    @app.get("/api/demos")
    async def demos() -> dict[str, Any]:
        return {"demos": list_demos()}

    @app.post("/api/sessions")
    async def create_session(body: CreateSession, request: Request) -> JSONResponse:
        client_ip = request.client.host if request.client else "unknown"

        if body.mode == "demo" and body.demo_id is not None:
            if len(body.research_text) > settings.max_research_chars:
                return _refusal(
                    413,
                    "input_too_large",
                    f"research_text exceeds the {settings.max_research_chars}-character ceiling",
                )
            try:
                inputs = demo_inputs(body.demo_id)
            except KeyError:
                return _refusal(404, "unknown_demo", f"no demo named {body.demo_id!r}")
        else:
            oversize = _oversize(body, settings)
            if oversize is not None:
                return oversize
            if not body.jd_text.strip() or not body.evidence_text.strip():
                return _refusal(400, "missing_input", "jd_text and evidence_text are required")
            inputs = {
                "job_description": body.jd_text,
                "evidence_source": body.evidence_text,
                "evidence_format": body.evidence_format,
                "round_text": body.round_text,
            }

        if body.mode == "live":
            refusal = _missing_credentials(body)
            if refusal is not None:
                return refusal

        session = store.create(
            client_ip=client_ip,
            mode=body.mode,
            demo_id=body.demo_id if body.mode == "demo" else None,
            provider=body.provider,
            api_key=(
                (body.gemini_api_key if body.provider == "gemini" else body.azure_api_key)
                if body.mode == "live"
                else None
            ),
            search_api_key=body.tavily_api_key if body.mode == "live" else None,
            azure_endpoint=body.azure_endpoint if body.mode == "live" else None,
            azure_deployment=body.azure_deployment if body.mode == "live" else None,
            research_text=body.research_text,
            **inputs,
        )
        return JSONResponse(status_code=201, content={"session_id": session.session_id})

    @app.get("/api/sessions/{session_id}")
    async def session_view(session_id: str) -> dict[str, Any]:
        return store.get(session_id).public_view()

    @app.get("/api/sessions/{session_id}/artifacts")
    async def artifacts(session_id: str) -> Any:
        session = store.get(session_id)
        if session.status != "completed":
            return _refusal(
                409,
                "not_completed",
                f"artifacts exist only for completed sessions; this one is {session.status}",
            )
        files: dict[str, Any] = {}
        for path in sorted(session.artifacts_dir.glob("*.json")):
            files[path.name] = json.loads(path.read_text(encoding="utf-8"))
        return {"session_id": session_id, "files": files}

    @app.websocket("/api/sessions/{session_id}/stream")
    async def stream(websocket: WebSocket, session_id: str) -> None:
        try:
            session = store.get(session_id)
        except SessionRefused as exc:
            await websocket.close(code=4404, reason=exc.message)
            return
        if session.status != "created":
            await websocket.close(code=4409, reason=f"session is {session.status}")
            return
        await websocket.accept()

        model = _build_session_model(session)
        if isinstance(model, dict):
            await websocket.send_json(model)
            await websocket.close(code=4400)
            return

        start_run(session, settings, model)
        try:
            while True:
                event = await asyncio.to_thread(session.events.get)
                await websocket.send_json(event)
                if event["type"] == "interrupt":
                    answer = await _receive_answer(websocket, settings)
                    if answer is None:
                        continue  # the refusal was sent; wait for a retry
                    session.answers.put(answer)
                elif event["type"] == "done":
                    break
        except WebSocketDisconnect:
            session.answers.put(DISCONNECTED)
            return
        await websocket.close()

    # The built web app, when present. Mounted last, so /api and the socket
    # always win; absent in development and in CI, where only the API runs.
    web_dist = _find_web_dist()
    if web_dist is not None:
        app.mount("/", StaticFiles(directory=web_dist, html=True), name="web")

    return app


def _find_web_dist() -> Path | None:
    """Locate the built web app, or None when it has not been built.

    Three candidates, in order: an explicit override, the working directory
    (how the container is laid out, with the package installed into
    site-packages), and the repository checkout relative to this file (how a
    development run is laid out).
    """
    override = os.environ.get("WEB_DIST_DIR")
    candidates = [
        Path(override) if override else None,
        Path.cwd() / "web" / "dist",
        Path(__file__).resolve().parents[3] / "web" / "dist",
    ]
    for candidate in candidates:
        if candidate is not None and candidate.is_dir():
            return candidate
    return None


def _missing_credentials(body: CreateSession) -> JSONResponse | None:
    """Refuse a live session whose provider credentials are incomplete."""
    if body.provider == "gemini":
        if not body.gemini_api_key:
            return _refusal(
                400,
                "missing_credentials",
                "live mode with the gemini provider needs gemini_api_key; "
                "use demo mode to run without one",
            )
        return None
    missing = [
        name
        for name, value in (
            ("azure_api_key", body.azure_api_key),
            ("azure_endpoint", body.azure_endpoint),
            ("azure_deployment", body.azure_deployment),
        )
        if not value
    ]
    if missing:
        return _refusal(
            400,
            "missing_credentials",
            "live mode with the azure provider needs "
            + " and ".join(missing)
            + "; use demo mode to run without credentials",
        )
    return None


def _oversize(body: CreateSession, settings: Settings) -> JSONResponse | None:
    checks = (
        ("jd_text", body.jd_text, settings.max_jd_chars),
        ("evidence_text", body.evidence_text, settings.max_evidence_chars),
        ("round_text", body.round_text, settings.max_round_chars),
        ("research_text", body.research_text, settings.max_research_chars),
    )
    for name, value, ceiling in checks:
        if len(value) > ceiling:
            return _refusal(
                413,
                "input_too_large",
                f"{name} exceeds the {ceiling}-character ceiling",
            )
    return None


def _build_session_model(session):
    """Resolve the session's provider, or an error event if it cannot be."""
    if session.mode == "demo":
        return demo_provider(session.demo_id)
    try:
        from ..providers import build_model

        if session.provider == "azure":
            return build_model(
                "azure",
                api_key=session.api_key,
                endpoint=session.azure_endpoint,
                deployment=session.azure_deployment,
            )
        return build_model("gemini", api_key=session.api_key)
    except ProviderError as error:
        session.status = "failed"
        session.error = {"category": "provider", "message": str(error)}
        return {"type": "error", "category": "provider", "message": str(error)}


async def _receive_answer(websocket: WebSocket, settings: Settings) -> str | None:
    """Read one answer message; refuse oversized or malformed ones in place."""
    while True:
        message = await websocket.receive_json()
        if message.get("type") != "answer" or "text" not in message:
            await websocket.send_json(
                {
                    "type": "error",
                    "category": "bad_message",
                    "message": 'expected {"type": "answer", "text": ...}',
                }
            )
            continue
        text = str(message["text"])
        if len(text) > settings.max_answer_chars:
            await websocket.send_json(
                {
                    "type": "error",
                    "category": "input_too_large",
                    "message": (
                        f"answer exceeds the {settings.max_answer_chars}-character ceiling"
                    ),
                }
            )
            continue
        return text


async def _cleanup_loop(store: SessionStore) -> None:
    while True:
        await asyncio.sleep(CLEANUP_INTERVAL_SECONDS)
        store.evict_expired()
