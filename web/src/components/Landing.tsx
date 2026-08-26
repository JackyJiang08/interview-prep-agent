import {
  useEffect,
  useReducer,
  useRef,
  useState,
  type DragEvent,
  type FormEvent,
} from "react";

import { createSession, extractResume, fetchDemos, type CreateSessionBody } from "../api";
import { displayTitle, SAMPLE_DEMO_ID } from "../demos";
import { disclosureReducer, initialDisclosure, type Section } from "../disclosure";
import {
  describeKind,
  detectEvidenceFormat,
  EVIDENCE_EXTENSIONS,
  isPdf,
  overCeiling,
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

type Provider = "gemini" | "azure" | "anthropic";

const KEY_LABELS: Record<Provider, string> = {
  gemini: "Gemini API key",
  azure: "Azure OpenAI API key",
  anthropic: "Anthropic API key",
};

// A loaded resume: where it came from, and the text that will be used.
interface Resume {
  filename: string | null;
  text: string;
}

export function Landing({ onStart }: { onStart: (sessionId: string) => void }) {
  const [demos, setDemos] = useState<Demo[] | null>(null);
  const [wake, dispatchWake] = useReducer(wakeReducer, initialWakeState);
  const [open, dispatchOpen] = useReducer(disclosureReducer, initialDisclosure);
  const [starting, dispatchStart] = useReducer(startReducer, idleStart);
  const busy = starting.phase === "starting";

  // The form.
  const [jdText, setJdText] = useState("");
  const [resume, setResume] = useState<Resume>({ filename: null, text: "" });
  const [override, setOverride] = useState<EvidenceFormat | null>(null);
  const [apiKey, setApiKey] = useState("");

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
  const detected = detectEvidenceFormat(resume.text);
  const format = override ?? detected;

  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (resume.text.trim() === "") {
      refuse("own", "add your resume first - drop a file, or open the text box and paste it");
      return;
    }
    const refusal =
      overCeiling("jd_text", jdText.length) ??
      overCeiling("evidence_text", resume.text.length) ??
      overCeiling("round_text", roundText.length) ??
      overCeiling("research_text", researchText.length);
    if (refusal !== null) {
      refuse("own", refusal);
      return;
    }
    void start("own", {
      mode: "live",
      jd_text: jdText,
      evidence_text: resume.text,
      evidence_format: format,
      provider,
      ...(provider === "gemini"
        ? { gemini_api_key: apiKey }
        : provider === "azure"
          ? { azure_api_key: apiKey }
          : { anthropic_api_key: apiKey }),
      round_text: roundText,
      research_text: researchText,
      tavily_api_key: searchKey || undefined,
      azure_endpoint: azureEndpoint || undefined,
      azure_deployment: azureDeployment || undefined,
    });
  };

  return (
    <div className="landing">
      <section className="card" aria-label="Prepare for a posting">
        <h2>Prepare for a posting</h2>
        <form onSubmit={submit}>
          <p className="empty-note sample-line">
            No key?{" "}
            <button
              type="button"
              className="plain"
              disabled={busy || !ready}
              onClick={() => runDemo("sample", SAMPLE_DEMO_ID)}
            >
              Run the sample
            </button>{" "}
            - a data analyst posting. You answer three questions; the gates decide
            what counts.
          </p>
          {wake.phase === "waking" && (
            <p className="empty-note" role="status">
              Starting the server — this demo sleeps when idle and takes a few
              seconds to wake.
            </p>
          )}
          {noticeAt("sample")}

          <label>
            Job posting
            <textarea
              rows={7}
              value={jdText}
              placeholder="Paste the posting here"
              required
              onChange={(event) => {
                setJdText(event.target.value);
                refuse("own", null);
              }}
            />
          </label>

          <ResumeDropZone
            resume={resume}
            format={format}
            previewOpen={open.preview}
            onTogglePreview={() => toggle("preview")}
            onLoaded={(loaded) => {
              setResume(loaded);
              setOverride(null);
              refuse("own", null);
            }}
            onOverride={() => setOverride(format === "yaml" ? "markdown" : "yaml")}
            onRefusal={(message) => refuse("own", message)}
          />

          <label>
            {KEY_LABELS[provider]}
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
          <button className="primary" type="submit" disabled={busy || !ready}>
            Start
          </button>
          {noticeAt("own")}
        </form>

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
              <label>
                <input
                  type="radio"
                  name="provider"
                  checked={provider === "anthropic"}
                  onChange={() => setProvider("anthropic")}
                />
                Claude
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

// The resume comes in as a file - dropped or browsed - and is read in the
// browser; only its text ever leaves, through the same request a paste would
// make. What was read is shown in a collapsed text box the visitor can open,
// correct, or simply paste into when there is no file.
function ResumeDropZone({
  resume,
  format,
  previewOpen,
  onTogglePreview,
  onLoaded,
  onOverride,
  onRefusal,
}: {
  resume: Resume;
  format: EvidenceFormat;
  previewOpen: boolean;
  onTogglePreview: () => void;
  onLoaded: (resume: Resume) => void;
  onOverride: () => void;
  onRefusal: (message: string) => void;
}) {
  const [dragging, setDragging] = useState(false);
  const [reading, setReading] = useState<string | null>(null);
  const picker = useRef<HTMLInputElement | null>(null);

  const take = async (file: File | undefined) => {
    if (file === undefined) return;
    if (isPdf(file.name)) {
      // The server reads PDFs; the wait is named, and its text is checked
      // against the same ceiling a paste would be.
      setReading(`Reading ${file.name}`);
      try {
        const { text } = await extractResume(file);
        const refusal = overCeiling("evidence_text", text.length);
        if (refusal !== null) onRefusal(`${refusal}; nothing was read`);
        else onLoaded({ filename: file.name, text });
      } catch (cause) {
        onRefusal(cause instanceof Error ? cause.message : "the PDF could not be read");
      } finally {
        setReading(null);
      }
      return;
    }
    const result = await readTextFile(file, EVIDENCE_EXTENSIONS, "evidence_text");
    if ("refusal" in result) onRefusal(result.refusal);
    else onLoaded({ filename: file.name, text: result.text });
  };

  const onDrop = (event: DragEvent<HTMLDivElement>) => {
    event.preventDefault();
    setDragging(false);
    void take(event.dataTransfer.files[0]);
  };

  const loaded = resume.filename !== null;
  const other = format === "yaml" ? "markdown" : "yaml";
  const browse = (
    <button type="button" className="plain" onClick={() => picker.current?.click()}>
      browse
    </button>
  );

  return (
    <div className="resume-field">
      <span className="field-label">Resume</span>
      <div
        className={dragging ? "drop-zone dragging" : "drop-zone"}
        onDragOver={(event) => {
          event.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={onDrop}
      >
        {reading !== null && (
          <span role="status">{reading}</span>
        )}
        {loaded ? (
          <>
            <span>
              <span className="file-name">{resume.filename}</span>
              {" - read as "}
              {describeKind(format, resume.filename)}
              {" · "}
              <button type="button" className="plain" onClick={onOverride}>
                read as {describeKind(other)} instead
              </button>
            </span>
            <span className="drop-again">Drop another file to replace it, or {browse}</span>
          </>
        ) : (
          <span>Drop your resume here - PDF, markdown, or YAML evidence · {browse}</span>
        )}
      </div>
      <input
        ref={picker}
        type="file"
        accept={EVIDENCE_EXTENSIONS.join(",")}
        hidden
        onChange={(event) => {
          void take(event.target.files?.[0]);
          event.target.value = "";
        }}
      />
      <button
        type="button"
        className="disclosure preview-toggle"
        aria-expanded={previewOpen}
        onClick={onTogglePreview}
      >
        {loaded ? "The text that will be used" : "No file? Paste your resume instead"}
      </button>
      {previewOpen && (
        <label className="preview">
          {loaded
            ? "Correct anything that was read wrongly; this text is what the run sees."
            : "Paste your resume as plain text or markdown, or a YAML evidence list."}
          <textarea
            rows={10}
            value={resume.text}
            onChange={(event) => onLoaded({ filename: resume.filename, text: event.target.value })}
          />
        </label>
      )}
    </div>
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
