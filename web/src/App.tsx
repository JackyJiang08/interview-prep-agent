import { useEffect, useReducer, useRef, useState } from "react";

import { streamUrl } from "./api";
import { InterruptCard, ResolutionCard } from "./components/InterruptCard";
import { Landing } from "./components/Landing";
import { PackageView } from "./components/PackageView";
import { StageRail } from "./components/StageRail";
import { initialRunState, runReducer } from "./reducer";

export default function App() {
  const [sessionId, setSessionId] = useState<string | null>(null);
  return (
    <>
      <header className="app-header">
        <h1>interview-prep-agent</h1>
        <span className="descriptor">
          Traceable interview preparation - models advise, deterministic gates
          admit.
        </span>
        <a
          href="https://github.com/JackyJiang08/interview-prep-agent"
          rel="noreferrer"
          target="_blank"
        >
          GitHub
        </a>
      </header>
      <main>
        {sessionId === null ? (
          <Landing onStart={setSessionId} />
        ) : (
          <RunScreen sessionId={sessionId} onReset={() => setSessionId(null)} />
        )}
      </main>
    </>
  );
}

function RunScreen({
  sessionId,
  onReset,
}: {
  sessionId: string;
  onReset: () => void;
}) {
  const [state, dispatch] = useReducer(runReducer, initialRunState);
  const socketRef = useRef<WebSocket | null>(null);

  useEffect(() => {
    const socket = new WebSocket(streamUrl(sessionId));
    socketRef.current = socket;
    socket.onmessage = (event) => {
      try {
        dispatch({ kind: "message", message: JSON.parse(event.data) });
      } catch {
        // a malformed frame changes nothing
      }
    };
    socket.onclose = () => dispatch({ kind: "socket_closed" });
    socket.onerror = () => dispatch({ kind: "socket_closed" });
    return () => socket.close();
  }, [sessionId]);

  const answer = (text: string) => {
    socketRef.current?.send(JSON.stringify({ type: "answer", text }));
    dispatch({ kind: "answer_submitted", text });
  };

  return (
    <div className="run-layout">
      <StageRail stages={state.stages} phase={state.phase} />
      <section aria-label="Session">
        {state.resolutions.map((resolution, index) => (
          <ResolutionCard key={index} resolution={resolution} />
        ))}
        {state.pending !== null && (
          <InterruptCard
            pending={state.pending}
            assessing={state.phase === "assessing"}
            onAnswer={answer}
          />
        )}
        {state.phase === "connecting" && state.stages.length === 0 && (
          <p className="empty-note" role="status">
            Starting the run. The initial generation reads the posting and the
            evidence; questions appear only where a high-importance gap needs
            one.
          </p>
        )}
        {state.phase === "disconnected" && (
          <div className="terminal-card failed">
            <p className="stop">Session ended</p>
            <p className="empty-note">
              The connection closed before the run finished. Start a new
              session to run again; nothing from this one was kept.
            </p>
            <button className="primary" type="button" onClick={onReset}>
              Back to start
            </button>
          </div>
        )}
        {state.phase === "failed" && (
          <div className="terminal-card failed">
            <p className="stop">Run failed</p>
            {state.error !== null && (
              <p className="error-line">
                {state.error.category}: {state.error.message}
              </p>
            )}
            <button className="primary" type="button" onClick={onReset}>
              Back to start
            </button>
          </div>
        )}
        {state.phase === "completed" && (
          <div className="terminal-card">
            <p className="stop">
              {state.stopReason === "valid_package_complete"
                ? "Run complete - the package passed every gate."
                : `Run ended: ${state.stopReason ?? "no stop reason"}`}
            </p>
            <button className="primary" type="button" onClick={onReset}>
              Start another session
            </button>
          </div>
        )}
        {state.prepPackage !== null && (
          <PackageView
            prepPackage={state.prepPackage}
            evidence={state.evidence}
            research={state.research}
          />
        )}
      </section>
    </div>
  );
}
