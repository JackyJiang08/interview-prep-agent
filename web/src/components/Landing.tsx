import {
  useEffect,
  useReducer,
  useRef,
  useState,
  type DragEvent,
  type ReactNode,
} from "react";

import { createSession, fetchDemos, type CreateSessionBody } from "../api";
import { displayTitle, SAMPLE_DEMO_ID, SAMPLE_DISPLAY_NAME } from "../demos";
import { disclosureReducer, initialDisclosure, type Section } from "../disclosure";
import {
  detectEvidenceFormat,
  EVIDENCE_EXTENSIONS,
  overCeiling,
  POSTING_EXTENSIONS,
  readTextFile,
  type BoundedField,
  type EvidenceFormat,
} from "../inputs";
import {
  idleStart,
  SLOW_START_MS,
  startReducer,
  visibleLine,
  type StartWhere,
} from "../start";
import type { Demo } from "../types";
import {
  FETCH_TIMEOUT_MS,
  initialWakeState,
  retryDelayMs,
  wakeReducer,
} from "../wake";

type Provider = "gemini" | "azure";

export function Landing({ onStart }: { onStart: (sessionId: string) => void }) {
  const [demos, setDemos] = useState<Demo[] | null>(null);
  const [wake, dispatchWake] = useReducer(wakeReducer, initialWakeState);
  const [open, dispatchOpen] = useReducer(disclosureReducer, initialDisclosure);
  const [starting, dispatchStart] = useReducer(startReducer, idleStart);
  const busy = starting.phase === "starting";

  // Advanced options ride along with every run, including the demos, so a
  // visitor who wrote research notes sees them used.
  const [provider, setProvider] = useState<Provider>("gemini");
  const [roundText, setRoundText] = useState("");
  const [researchText, setResearchText] = useState("");
  const [searchKey, setSearchKey] = useState("");
  const [azureEndpoint, setAzureEndpoint] = useState("");
  const [azureDeployment, setAzureDeployment] = useState("");

  useEffect(() => {
    if (wake.phase === "ready") return;
    let cancelled = false;
    const timer = window.setTimeout(() => {
      fetchDemos(FETCH_TIMEOUT_MS)
        .then((list) => {
          if (cancelled) return;
          setDemos(list);
          dispatchWake({ kind: "loaded" });
        })
        .catch(() => {
          if (!cancelled) dispatchWake({ kind: "attempt_failed" });
        });
    }, retryDelayMs(wake.attempt));
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [wake]);

  // Past a warm server's answer time, the wait is named as a wake.
  useEffect(() => {
    if (starting.phase !== "starting" || starting.slow) return;
    const timer = window.setTimeout(
      () => dispatchStart({ kind: "still_waiting" }),
      SLOW_START_MS,
    );
    return () => window.clearTimeout(timer);
  }, [starting]);

  const start = async (where: StartWhere, body: CreateSessionBody) => {
    dispatchStart({ kind: "clicked", where });
    try {
      onStart(await createSession(body));
    } catch (cause) {
      dispatchStart({
        kind: "failed",
        message: cause instanceof Error ? cause.message : "the session could not be started",
      });
    }
  };

  const runDemo = (where: StartWhere, demoId: string) =>
    start(where, { mode: "demo", demo_id: demoId, research_text: researchText });

  // A refusal the page itself makes, before any request, reads like a failed
  // start: it followed a click, so it is shown where the click happened.
  const refuse = (where: StartWhere, message: string | null) => {
    if (message === null) {
      dispatchStart({ kind: "dismissed" });
      return;
    }
    dispatchStart({ kind: "clicked", where });
    dispatchStart({ kind: "failed", message });
  };

  // The one line for the action at this spot, or nothing when idle there.
  const noticeAt = (where: StartWhere) => {
    if (starting.phase === "idle" || starting.where !== where) return null;
    const line = visibleLine(starting);
    return starting.phase === "failed" ? (
      <p className="error-line" role="alert">
        {line}
      </p>
    ) : (
      <p className="empty-note" role="status">
        {line}
      </p>
    );
  };

  const ready = wake.phase === "ready";
  const toggle = (section: Section) => dispatchOpen({ kind: "toggle", section });

  return (
    <div className="landing">
      <section className="hero" aria-label="Sample run">
        <p className="hero-name">{SAMPLE_DISPLAY_NAME}</p>
        <button
          className="primary hero-action"
          type="button"
          disabled={busy || !ready}
          onClick={() => runDemo("sample", SAMPLE_DEMO_ID)}
        >
          Run the sample
        </button>
        <p className="empty-note">
          No key needed. You answer three questions about your experience; the
          gates decide what counts.
        </p>
        {wake.phase === "waking" && (
          <p className="empty-note" role="status">
            Starting the server — this demo sleeps when idle and takes a few
            seconds to wake.
          </p>
        )}
        {noticeAt("sample")}
      </section>

      <section className="own-posting" aria-label="Use your own posting">
        <h2>Use your own posting</h2>
        <OwnPostingForm
          busy={busy || !ready}
          provider={provider}
          advanced={{
            round_text: roundText,
            research_text: researchText,
            tavily_api_key: searchKey || undefined,
            azure_endpoint: azureEndpoint || undefined,
            azure_deployment: azureDeployment || undefined,
          }}
          onRefusal={(message) => refuse("own", message)}
          onSubmit={(body) => start("own", body)}
        />
        {noticeAt("own")}
        <button
          type="button"
          className="disclosure"
          aria-expanded={open.advanced}
          onClick={() => toggle("advanced")}
        >
          Advanced options
        </button>
        {open.advanced && (
          <div className="advanced">
            <fieldset className="choice-row">
              <legend className="empty-note">
                Model provider - the key above belongs to whichever you pick
              </legend>
              <label>
                <input
                  type="radio"
                  name="provider"
                  checked={provider === "gemini"}
                  onChange={() => setProvider("gemini")}
                />
                Gemini
              </label>
              <label>
                <input
                  type="radio"
                  name="provider"
                  checked={provider === "azure"}
                  onChange={() => setProvider("azure")}
                />
                Azure OpenAI
              </label>
            </fieldset>
            {provider === "azure" && (
              <>
                <label>
                  Azure OpenAI endpoint - the resource URL from your Azure portal
                  <input
                    type="text"
                    value={azureEndpoint}
                    onChange={(event) => setAzureEndpoint(event.target.value)}
                  />
                </label>
                <label>
                  Azure OpenAI deployment - the name you gave the model deployment
                  <input
                    type="text"
                    value={azureDeployment}
                    onChange={(event) => setAzureDeployment(event.target.value)}
                  />
                </label>
              </>
            )}
            <BoundedTextInput
              label="Upcoming round, optional - shapes the strategy and the practice questions, never which requirements count as covered"
              field="round_text"
              rows={1}
              value={roundText}
              onChange={setRoundText}
            />
            <BoundedTextInput
              label="Role research, optional - notes or excerpts you have gathered about the team or the role. They sharpen the strategy and the questions; they never count as evidence"
              field="research_text"
              rows={3}
              value={researchText}
              onChange={setResearchText}
            />
            <label>
              Search API key, optional - lets the run look up the role itself
              instead of relying on your notes alone
              <input
                type="password"
                value={searchKey}
                onChange={(event) => setSearchKey(event.target.value)}
                autoComplete="off"
              />
            </label>
          </div>
        )}
      </section>

      <section className="engineering" aria-label="Engineering demos">
        <button
          type="button"
          className="disclosure"
          aria-expanded={open.demos}
          onClick={() => toggle("demos")}
        >
          Engineering demos
        </button>
        {open.demos && (
          <div className="demo-list">
            <p className="empty-note">
              Each demo replays one of the regression scenarios: the fixture
              provider stands in for the model, so no key is needed and every
              verdict is deterministic. You answer the questions; the admission
              gates decide.
            </p>
            {(demos ?? []).map((demo) => (
              <div className="demo-row" key={demo.demo_id}>
                <div className="demo-text">
                  <span className="demo-title">{displayTitle(demo.demo_id)}</span>
                  <span className="demo-id mono">{demo.demo_id}</span>
                  <p>{demo.description}</p>
                </div>
                <button
                  type="button"
                  className="primary"
                  disabled={busy || !ready}
                  onClick={() => runDemo("demos", demo.demo_id)}
                >
                  Run
                </button>
              </div>
            ))}
            {noticeAt("demos")}
          </div>
        )}
      </section>
    </div>
  );
}

function OwnPostingForm({
  busy,
  provider,
  advanced,
  onRefusal,
  onSubmit,
}: {
  busy: boolean;
  provider: Provider;
  advanced: Pick<
    CreateSessionBody,
    "round_text" | "research_text" | "tavily_api_key" | "azure_endpoint" | "azure_deployment"
  >;
  onRefusal: (message: string | null) => void;
  onSubmit: (body: CreateSessionBody) => void;
}) {
  const [jdText, setJdText] = useState("");
  const [evidenceText, setEvidenceText] = useState("");
  const [override, setOverride] = useState<EvidenceFormat | null>(null);
  const [apiKey, setApiKey] = useState("");

  const detected = detectEvidenceFormat(evidenceText);
  const format = override ?? detected;

  const submit = () => {
    const refusal =
      overCeiling("jd_text", jdText.length) ??
      overCeiling("evidence_text", evidenceText.length) ??
      overCeiling("round_text", (advanced.round_text ?? "").length) ??
      overCeiling("research_text", (advanced.research_text ?? "").length);
    if (refusal !== null) {
      onRefusal(refusal);
      return;
    }
    onRefusal(null);
    onSubmit({
      mode: "live",
      jd_text: jdText,
      evidence_text: evidenceText,
      evidence_format: format,
      provider,
      ...(provider === "gemini" ? { gemini_api_key: apiKey } : { azure_api_key: apiKey }),
      ...advanced,
    });
  };

  return (
    <form
      onSubmit={(event) => {
        event.preventDefault();
        submit();
      }}
    >
      <DropTextarea
        label="Job posting"
        hint={`Paste the posting, or drop a ${POSTING_EXTENSIONS.join(" or ")} file here`}
        field="jd_text"
        extensions={POSTING_EXTENSIONS}
        rows={7}
        value={jdText}
        onChange={(text) => {
          setJdText(text);
          onRefusal(null);
        }}
        onRefusal={onRefusal}
      />
      <DropTextarea
        label="Your resume or evidence"
        hint="Paste a resume in markdown, or drop a .md or .yaml file here"
        field="evidence_text"
        extensions={EVIDENCE_EXTENSIONS}
        rows={7}
        value={evidenceText}
        onChange={(text) => {
          setEvidenceText(text);
          setOverride(null);
          onRefusal(null);
        }}
        onRefusal={onRefusal}
        footer={
          evidenceText.trim() !== "" && (
            <span className="format-label">
              Read as {format === "yaml" ? "a structured evidence list" : "a resume"}
              {" · "}
              <button
                type="button"
                className="plain"
                onClick={() => setOverride(format === "yaml" ? "markdown" : "yaml")}
              >
                read as {format === "yaml" ? "a resume" : "a structured evidence list"} instead
              </button>
            </span>
          )
        }
      />
      <label>
        {provider === "gemini" ? "Gemini API key" : "Azure OpenAI API key"}
        <input
          type="password"
          value={apiKey}
          onChange={(event) => setApiKey(event.target.value)}
          autoComplete="off"
          required
        />
      </label>
      <p className="key-notice">
        Keys are held in this page's memory, sent once to create the session,
        never stored in this browser, and dropped with the session on the
        server.
      </p>
      <button className="primary" type="submit" disabled={busy}>
        Start with my posting
      </button>
    </form>
  );
}

// A textarea that also takes a dropped or picked file. The file is read in
// the browser; only its text ever leaves, through the same request a paste
// would make.
function DropTextarea({
  label,
  hint,
  field,
  extensions,
  rows,
  value,
  onChange,
  onRefusal,
  footer,
}: {
  label: string;
  hint: string;
  field: BoundedField;
  extensions: string[];
  rows: number;
  value: string;
  onChange: (text: string) => void;
  onRefusal: (message: string) => void;
  footer?: ReactNode;
}) {
  const [dragging, setDragging] = useState(false);
  const picker = useRef<HTMLInputElement | null>(null);

  const take = async (file: File | undefined) => {
    if (file === undefined) return;
    const result = await readTextFile(file, extensions, field);
    if ("refusal" in result) onRefusal(result.refusal);
    else onChange(result.text);
  };

  const onDrop = (event: DragEvent<HTMLTextAreaElement>) => {
    event.preventDefault();
    setDragging(false);
    void take(event.dataTransfer.files[0]);
  };

  return (
    <label className={dragging ? "drop-target dragging" : "drop-target"}>
      <span className="field-head">
        {label}
        <button type="button" className="plain" onClick={() => picker.current?.click()}>
          pick a file
        </button>
      </span>
      <textarea
        rows={rows}
        value={value}
        placeholder={hint}
        required
        onChange={(event) => onChange(event.target.value)}
        onDragOver={(event) => {
          event.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={onDrop}
      />
      <input
        ref={picker}
        type="file"
        accept={extensions.join(",")}
        hidden
        onChange={(event) => {
          void take(event.target.files?.[0]);
          event.target.value = "";
        }}
      />
      {footer}
    </label>
  );
}

function BoundedTextInput({
  label,
  field,
  rows,
  value,
  onChange,
}: {
  label: string;
  field: BoundedField;
  rows: number;
  value: string;
  onChange: (text: string) => void;
}) {
  const refusal = overCeiling(field, value.length);
  return (
    <label>
      {label}
      <textarea rows={rows} value={value} onChange={(event) => onChange(event.target.value)} />
      {refusal !== null && <span className="error-line">{refusal}</span>}
    </label>
  );
}
