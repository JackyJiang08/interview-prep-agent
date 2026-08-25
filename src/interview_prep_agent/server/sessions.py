"""In-memory session store with the same bounded discipline the agent has.

Every bound is a setting, every violation is a structured refusal, and an
expired or denied session says so plainly. A live session's provider key
lives only on the session object in memory: it is never logged, never
written to disk, never echoed back, and is dropped with the session.
"""

from __future__ import annotations

import shutil
import tempfile
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from queue import Queue
from typing import Any


class SessionRefused(Exception):
    """A request the store declines, with a status and a category."""

    def __init__(self, status_code: int, category: str, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.category = category
        self.message = message


@dataclass
class Session:
    """One web session over one agent thread."""

    session_id: str
    mode: str
    client_ip: str
    job_description: str
    evidence_source: str
    evidence_format: str
    round_text: str
    artifacts_dir: Path
    demo_id: str | None = None
    # Live-mode credential. In memory only, for the provider construction;
    # excluded from every serialization of the session.
    api_key: str | None = None
    status: str = "created"
    stop_reason: str | None = None
    error: dict[str, str] | None = None
    created_at: float = field(default_factory=time.monotonic)
    # Bridges between the worker thread and the socket handler.
    events: Queue = field(default_factory=Queue)
    answers: Queue = field(default_factory=Queue)

    def public_view(self) -> dict[str, Any]:
        """The session as clients may see it. The key is not in it."""
        return {
            "session_id": self.session_id,
            "mode": self.mode,
            "demo_id": self.demo_id,
            "status": self.status,
            "stop_reason": self.stop_reason,
            "error": self.error,
        }


class SessionStore:
    """Thread-safe registry enforcing the session bounds."""

    def __init__(
        self,
        max_concurrent_sessions: int,
        max_sessions_per_ip: int,
        session_ttl_seconds: int,
    ) -> None:
        self.max_concurrent_sessions = max_concurrent_sessions
        self.max_sessions_per_ip = max_sessions_per_ip
        self.session_ttl_seconds = session_ttl_seconds
        self._sessions: dict[str, Session] = {}
        self._lock = threading.Lock()
        self._temp_root = Path(tempfile.mkdtemp(prefix="prep-sessions-"))

    def create(self, *, client_ip: str, **fields: Any) -> Session:
        """Register a session, or refuse with the bound that was hit."""
        with self._lock:
            self._evict_expired_locked()
            if len(self._sessions) >= self.max_concurrent_sessions:
                raise SessionRefused(
                    429,
                    "session_limit",
                    f"at most {self.max_concurrent_sessions} concurrent "
                    "sessions; retry after one completes or expires",
                )
            owned = sum(1 for item in self._sessions.values() if item.client_ip == client_ip)
            if owned >= self.max_sessions_per_ip:
                raise SessionRefused(
                    429,
                    "per_ip_limit",
                    f"at most {self.max_sessions_per_ip} sessions per client",
                )
            session_id = uuid.uuid4().hex
            artifacts_dir = self._temp_root / session_id
            artifacts_dir.mkdir(parents=True)
            session = Session(
                session_id=session_id,
                client_ip=client_ip,
                artifacts_dir=artifacts_dir,
                **fields,
            )
            self._sessions[session_id] = session
            return session

    def get(self, session_id: str) -> Session:
        """Resolve a session; an unknown or expired one says which it is."""
        with self._lock:
            self._evict_expired_locked()
            session = self._sessions.get(session_id)
        if session is None:
            raise SessionRefused(
                404,
                "unknown_session",
                "no such session; it may have expired and been removed",
            )
        return session

    def evict_expired(self) -> int:
        """Drop sessions past their TTL; returns how many were removed."""
        with self._lock:
            return self._evict_expired_locked()

    def _evict_expired_locked(self) -> int:
        now = time.monotonic()
        expired = [
            session_id
            for session_id, session in self._sessions.items()
            if now - session.created_at > self.session_ttl_seconds
        ]
        for session_id in expired:
            self._drop_locked(session_id)
        return len(expired)

    def drop(self, session_id: str) -> None:
        with self._lock:
            self._drop_locked(session_id)

    def _drop_locked(self, session_id: str) -> None:
        session = self._sessions.pop(session_id, None)
        if session is None:
            return
        # The key dies with the session.
        session.api_key = None
        shutil.rmtree(session.artifacts_dir, ignore_errors=True)

    def active_count(self) -> int:
        with self._lock:
            return len(self._sessions)
