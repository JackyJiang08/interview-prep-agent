import { useEffect, useState } from "react";

import { createSession, fetchDemos, type CreateSessionBody } from "../api";
import type { Demo } from "../types";

export function Landing({ onStart }: { onStart: (sessionId: string) => void }) {
  const [demos, setDemos] = useState<Demo[] | null>(null);
  const [ownKey, setOwnKey] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    fetchDemos()
      .then(setDemos)
      .catch(() => setError("could not load the demo list; is the server running?"));
  }, []);

  const start = async (body: CreateSessionBody) => {
    setBusy(true);
    setError(null);
    try {
      onStart(await createSession(body));
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "session creation failed");
      setBusy(false);
    }
  };

  return (
    <div>
      <section aria-label="Demos">
        <h2>Run a committed demo</h2>
        <p className="empty-note">
          Each demo replays one of the regression scenarios: the fixture
          provider stands in for the model, so no key is needed and every
          verdict is deterministic. You answer the questions; the admission
          gates decide.
        </p>
        {error !== null && <p className="error-line">{error}</p>}
        <div className="landing-grid">
          {(demos ?? []).map((demo) => (
            <button
              key={demo.demo_id}
              type="button"
              className="demo-card"
              disabled={busy}
              onClick={() => start({ mode: "demo", demo_id: demo.demo_id })}
            >
              <span className="demo-id">{demo.demo_id}</span>
              <p>{demo.description}</p>
            </button>
          ))}
        </div>
      </section>

      <section className="own-key" aria-label="Run with your own key">
        {ownKey ? (
          <OwnKeyForm busy={busy} onSubmit={start} />
        ) : (
          <p className="empty-note">
            Or{" "}
            <button type="button" className="plain" onClick={() => setOwnKey(true)}>
              bring your own key
            </button>{" "}
            to run a live session over your own posting and evidence.
          </p>
        )}
      </section>
    </div>
  );
}

function OwnKeyForm({
  busy,
  onSubmit,
}: {
  busy: boolean;
  onSubmit: (body: CreateSessionBody) => void;
}) {
  const [jdText, setJdText] = useState("");
  const [evidenceText, setEvidenceText] = useState("");
  const [format, setFormat] = useState<"yaml" | "markdown">("yaml");
  const [roundText, setRoundText] = useState("");
  const [apiKey, setApiKey] = useState("");

  return (
    <form
      onSubmit={(event) => {
        event.preventDefault();
        onSubmit({
          mode: "live",
          jd_text: jdText,
          evidence_text: evidenceText,
          evidence_format: format,
          round_text: roundText,
          gemini_api_key: apiKey,
        });
      }}
    >
      <h2>Bring your own key</h2>
      <label>
        Job posting text
        <textarea
          rows={6}
          value={jdText}
          onChange={(event) => setJdText(event.target.value)}
          required
        />
      </label>
      <label>
        Evidence - a YAML corpus or a markdown resume
        <textarea
          rows={6}
          value={evidenceText}
          onChange={(event) => setEvidenceText(event.target.value)}
          required
        />
      </label>
      <fieldset className="format-toggle">
        <legend className="empty-note">Evidence format</legend>
        <label>
          <input
            type="radio"
            name="format"
            checked={format === "yaml"}
            onChange={() => setFormat("yaml")}
          />
          YAML corpus
        </label>
        <label>
          <input
            type="radio"
            name="format"
            checked={format === "markdown"}
            onChange={() => setFormat("markdown")}
          />
          markdown resume
        </label>
      </fieldset>
      <label>
        Upcoming round, optional - tailors strategy and questions, never matching
        <input
          type="text"
          value={roundText}
          onChange={(event) => setRoundText(event.target.value)}
        />
      </label>
      <label>
        Gemini API key
        <input
          type="password"
          value={apiKey}
          onChange={(event) => setApiKey(event.target.value)}
          autoComplete="off"
          required
        />
      </label>
      <p className="key-notice">
        The key is held in this page's memory, sent once to create the session,
        never stored in this browser, and dropped with the session on the
        server.
      </p>
      <button className="primary" type="submit" disabled={busy}>
        Start live session
      </button>
    </form>
  );
}
