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
from ..search import SearchError, SearchProvider
from ..workflow.gates import QualityGateError
from ..workflow.graph import PROGRESS_STAGES
from ..workflow.pipeline import _resolve_extractor, _resolve_matcher
from .sessions import Session

# Sentinel put on the answer queue when the client goes away, so the blocked
# ask callback ends the run instead of waiting forever.
DISCONNECTED = object()


class ClientGone(Exception):
    """The client disconnected while an answer was pending."""


def _business_delta(entry: dict[str, Any]) -> dict[str, Any]:
    """A trace entry reduced to its client-safe business content."""
    return {key: value for key, value in entry.items() if key != "node"}


def build_session_search(session: Session) -> SearchProvider | None:
    """The session's search provider, or None when no key was supplied."""
    if session.mode != "live" or not session.search_api_key:
        return None
    from ..search.tavily import TavilySearch

    try:
        return TavilySearch(api_key=session.search_api_key)
    except SearchError:
        return None


def start_run(session: Session, settings: Settings, model: StructuredModel) -> None:
    """Run the session's agent thread; every outcome lands on the event queue."""

    def on_event(entry: dict[str, Any]) -> None:
        session.events.put(
            {"type": "node_update", "node": entry["node"], "delta": _business_delta(entry)}
        )

    def on_stage(name: str) -> None:
        # Progress inside a generation, so the page can say which of the
        # known stages is running. Stages outside the named set stay quiet.
        if name in PROGRESS_STAGES:
            session.events.put(
                {
                    "type": "progress",
                    "stage": name,
                    "index": PROGRESS_STAGES.index(name) + 1,
                    "total": len(PROGRESS_STAGES),
                }
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
                # The root cause of a live run that read section headings as
                # requirements: these two were never passed, so every session
                # ran the lexical stages regardless of the key it carried.
                extractor=_resolve_extractor(session.extractor, model),
                matcher=_resolve_matcher(session.matcher, model),
                round_text=session.round_text,
                research_text=session.research_text,
                company=session.company,
                role_title=session.role_title,
                search=build_session_search(session),
                thread_id=session.session_id,
                on_event=on_event,
                on_stage=on_stage,
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
            # The evidence corpus rides along so every EV-/CL- citation in the
            # package can be opened with its provenance client-side.
            session.events.put(
                {
                    "type": "package",
                    "package": package.model_dump(mode="json", exclude_none=True),
                    "evidence": [
                        item.model_dump(mode="json", exclude_none=True)
                        for item in state.get("evidence") or []
                    ],
                    "research": [
                        item.model_dump(mode="json", exclude_none=True)
                        for item in state.get("research_findings") or []
                    ],
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
