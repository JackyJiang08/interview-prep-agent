import { useEffect, useRef, useState } from "react";

import type { PendingInterrupt, Resolution } from "../reducer";

function requirementText(question: string): string | null {
  const marker = "this requirement: ";
  const start = question.indexOf(marker);
  if (start === -1) return null;
  const rest = question.slice(start + marker.length);
  const end = rest.indexOf(". Include");
  return end === -1 ? rest : rest.slice(0, end);
}

export function InterruptCard({
  pending,
  assessing,
  onAnswer,
}: {
  pending: PendingInterrupt;
  assessing: boolean;
  onAnswer: (text: string) => void;
}) {
  const [text, setText] = useState("");
  const headingRef = useRef<HTMLHeadingElement>(null);

  useEffect(() => {
    headingRef.current?.focus();
  }, [pending.requirementId]);

  const requirement = requirementText(pending.question);
  return (
    <section className="interrupt-card" aria-label="Evidence question">
      <h3 tabIndex={-1} ref={headingRef}>
        One factual question
      </h3>
      <p className="req">
        Requirement <code>{pending.requirementId}</code>
        {requirement !== null && <>: {requirement}</>}
      </p>
      <p>{pending.question}</p>
      {assessing ? (
        <p className="empty-note" role="status">
          Assessing the answer against the admission gates...
        </p>
      ) : (
        <form
          onSubmit={(event) => {
            event.preventDefault();
            if (text.trim().length > 0) onAnswer(text);
          }}
        >
          <label>
            Your answer - one specific example, the method, the result
            <textarea
              rows={4}
              value={text}
              onChange={(event) => setText(event.target.value)}
              required
            />
          </label>
          <button className="primary" type="submit" disabled={text.trim() === ""}>
            Submit answer
          </button>
        </form>
      )}
    </section>
  );
}

export function ResolutionCard({ resolution }: { resolution: Resolution }) {
  return (
    <section
      className={`resolution-card ${resolution.accepted ? "admitted" : "rejected"}`}
      aria-label={`Answer for ${resolution.requirementId}: ${
        resolution.accepted ? "admitted" : "not admitted"
      }`}
    >
      <span className="verdict">
        {resolution.accepted ? "ADMITTED" : "RECORDED, NOT ADMITTED"}
      </span>
      <p className="req">
        Requirement <code>{resolution.requirementId}</code>
      </p>
      {resolution.accepted && resolution.acceptedClaim !== null ? (
        <p className="claim">
          {resolution.mintedId !== null && (
            <>
              <span className="chip" aria-hidden="true">
                {resolution.mintedId}
              </span>{" "}
            </>
          )}
          {resolution.acceptedClaim}
        </p>
      ) : (
        <p className="reason">
          The answer stays in the audit record and is never matched. Reason:{" "}
          {resolution.decisionReason}. The requirement remains an honest gap,
          surfaced in the strategy as a risk.
        </p>
      )}
    </section>
  );
}
