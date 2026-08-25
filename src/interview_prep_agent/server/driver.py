"""Drive one agent run per session on a worker thread.

The session's WebSocket is a projection of ``run_agent``'s existing
stream/interrupt/resume protocol: trace entries become ``node_update``
messages, the ask callback becomes an ``interrupt`` message that blocks until
the client's answer arrives, and the terminal state becomes ``package`` and
``done``. One driver serves both modes; only the injected provider differs.
"""

from __future__ import annotations

import threading
from typing import Any

from ..agent import run_agent
from ..config import Settings
from ..corpus import CorpusError
from ..providers import ProviderError, StructuredModel
from ..workflow.gates import QualityGateError
from .sessions import Session

# Sentinel put on the answer queue when the client goes away, so the blocked
# ask callback ends the run instead of waiting forever.
DISCONNECTED = object()


class ClientGone(Exception):
    """The client disconnected while an answer was pending."""


def _business_delta(entry: dict[str, Any]) -> dict[str, Any]:
    """A trace entry reduced to its client-safe business content."""
    return {key: value for key, value in entry.items() if key != "node"}


def start_run(session: Session, settings: Settings, model: StructuredModel) -> None:
    """Run the session's agent thread; every outcome lands on the event queue."""

    def on_event(entry: dict[str, Any]) -> None:
        session.events.put(
            {"type": "node_update", "node": entry["node"], "delta": _business_delta(entry)}
        )

    def ask(requirement_id: str, question: str) -> str:
        session.status = "waiting_for_answer"
        session.events.put(
            {
                "type": "interrupt",
                "requirement_id": requirement_id,
                "question": question,
                "context": {"mode": session.mode, "demo_id": session.demo_id},
            }
        )
        answer = session.answers.get()
        if answer is DISCONNECTED:
            raise ClientGone("the client disconnected before answering")
        session.status = "running"
        return str(answer)

    def work() -> None:
        session.status = "running"
        try:
            state, _trace = run_agent(
                session.job_description,
                session.evidence_source,
                "markdown" if session.evidence_format == "markdown" else "corpus",
                ask,
                settings,
                session.artifacts_dir,
                model=model,
                round_text=session.round_text,
                thread_id=session.session_id,
                on_event=on_event,
            )
        except ClientGone:
            session.status = "failed"
            session.error = {
                "category": "disconnected",
                "message": "the client disconnected before answering",
            }
            return
        except CorpusError as error:
            _fail(session, "input", str(error))
            return
        except QualityGateError as error:
            _fail(session, "gate", str(error))
            return
        except ProviderError as error:
            _fail(session, "provider", str(error))
            return
        except Exception:  # noqa: BLE001 - no stack traces cross the socket
            _fail(session, "internal", "the run failed unexpectedly")
            return

        session.status = "completed"
        session.stop_reason = state.get("stop_reason")
        package = state.get("prep_package")
        if package is not None:
            session.events.put(
                {
                    "type": "package",
                    "package": package.model_dump(mode="json", exclude_none=True),
                }
            )
        session.events.put({"type": "done", "stop_reason": session.stop_reason})

    thread = threading.Thread(target=work, name=f"session-{session.session_id}", daemon=True)
    thread.start()


def _fail(session: Session, category: str, message: str) -> None:
    session.status = "failed"
    session.error = {"category": category, "message": message}
    session.events.put({"type": "error", "category": category, "message": message})
    session.events.put({"type": "done", "stop_reason": None})
