import type { Phase, StageEntry } from "../reducer";
import { useElapsed } from "./ProgressLine";

const STAGE_LABELS: Record<string, string> = {
  parse_round: "Parse round",
  generate_initial: "Initial generation",
  observe: "Observe queue",
  ask: "Ask",
  assess_and_admit: "Assess and admit",
  generate_final: "Final generation",
  invalid: "Terminated",
  stop: "Stop",
};

const ACTIVE_PHASES: Phase[] = ["running", "waiting_for_answer", "assessing", "connecting"];

export function StageRail({ stages, phase }: { stages: StageEntry[]; phase: Phase }) {
  const running = ACTIVE_PHASES.includes(phase);
  return (
    <nav className="stage-rail" aria-label="Run stages">
      <h2>Run</h2>
      {stages.length === 0 ? (
        <p className="empty-note">
          Stages appear here as the run streams: round parsing, an initial
          generation, one question per evidence gap, then the final generation.
        </p>
      ) : (
        <ol aria-live="polite">
          {stages.map((entry, index) => {
            const current = running && index === stages.length - 1;
            return (
              <li key={index} className={current ? "current" : ""}>
                <span className="stage-name">
                  {STAGE_LABELS[entry.node] ?? entry.node}
                </span>
                {current && <CurrentElapsed startedAt={entry.startedAt} />}
                {entry.summary && (
                  <div className="stage-summary">{entry.summary}</div>
                )}
              </li>
            );
          })}
        </ol>
      )}
    </nav>
  );
}

// The active stage's running time, beside its name.
function CurrentElapsed({ startedAt }: { startedAt: number | null }) {
  const elapsed = useElapsed(startedAt);
  if (elapsed === null) return null;
  return <span className="stage-elapsed"> {elapsed}</span>;
}
