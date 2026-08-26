import { useEffect, useState } from "react";

import type { Progress } from "../reducer";

// A stage line while models run: which of the known stages, how long it has
// been running, and for the long model stages one quiet line about what is
// being produced. The bar is indeterminate on purpose; no number is faked.
export function ProgressLine({ progress }: { progress: Progress }) {
  const elapsed = useElapsed(progress.startedAt);
  return (
    <div className="progress" role="status" aria-live="polite">
      <p className="progress-line">
        Stage {progress.index} of {progress.total}: {progress.label}
        {elapsed !== null && <span className="elapsed"> {elapsed}</span>}
      </p>
      <div className="progress-bar" aria-hidden="true">
        <span />
      </div>
      {progress.note !== null && <p className="empty-note">{progress.note}</p>}
    </div>
  );
}

// Seconds since a wall-clock instant, refreshed once a second; null when the
// instant is unknown so nothing is invented.
export function useElapsed(startedAt: number | null): string | null {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (startedAt === null) return;
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, [startedAt]);
  if (startedAt === null) return null;
  return formatElapsed(Math.max(0, now - startedAt));
}

export function formatElapsed(milliseconds: number): string {
  const seconds = Math.floor(milliseconds / 1000);
  if (seconds < 60) return `${seconds}s`;
  return `${Math.floor(seconds / 60)}m ${String(seconds % 60).padStart(2, "0")}s`;
}
