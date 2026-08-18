# interview-prep-agent

[![CI](https://github.com/JackyJiang08/interview-prep-agent/actions/workflows/ci.yml/badge.svg)](https://github.com/JackyJiang08/interview-prep-agent/actions/workflows/ci.yml)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue)](pyproject.toml)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)

Turns a job posting plus attested experience — a YAML corpus or a markdown
resume — into a validated interview preparation package. Every claim cites
the source that justifies it, so a wrong answer is a wrong link a reader can
find and reject. The loop processes every evidence gap exactly once in a
deterministic order, admitting each answer through a model assessment plus a
code-owned gate — rejected answers are recorded in the audit trail, never
matched — and tailors strategy and questions to the stated next interview
round. Models advise; deterministic gates admit.

## Status

| Stage | Status |
|---|---|
| [Deterministic workflow](docs/ARCHITECTURE.md#layer-1--deterministic-workflow--shipped) — graph runtime, grounding and traceability gates | **shipped** |
| [Model-backed extraction](docs/METHODOLOGY.md#stage-1---extraction) — behind a provider seam, output never trusted raw | **shipped** |
| [Model-backed matching](docs/METHODOLOGY.md#stage-2---matching) — same seam, FULL/PARTIAL/GAP coverage; lexical stays the default | **shipped** |
| [Preparation package](docs/METHODOLOGY.md#stages-3-5---assessment-strategy-questions) — gap assessment, strategy, questions, package gate with a routed error branch | **shipped** |
| [Governed evidence loop](docs/ARCHITECTURE.md#layer-2--bounded-decision-layer--shipped-unevaluated) — every gap asked once, code-owned admission gate, round-aware regeneration | **shipped — unevaluated** |
| [Durable state](docs/ARCHITECTURE.md#layer-3--durable-state--planned) — same-thread resume already persists within a run; state across runs remains planned | planned |
| [Evaluation set + failure analysis](docs/ARCHITECTURE.md#cross-cutting--traces-evaluation-failure-analysis--planned) — gates most other work | planned |

## Quickstart

```bash
git clone https://github.com/JackyJiang08/interview-prep-agent.git
cd interview-prep-agent
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

PYTHONPATH=src python -m interview_prep_agent.cli match \
  --jd examples/sample_job_description.txt \
  --evidence examples/sample_evidence.yaml \
  --out out/
```

Runs offline on the committed synthetic example, no configuration or key:

```
Coverage: 6 requirements | 3 PROOF | 3 GAP
[GAP ] REQ-002 Experience designing and interpreting A/B tests
        No evidence item covers this requirement. Prepare it first.
[PROOF] REQ-003 Build and maintain ETL pipelines in a cloud data warehouse
        - EV-002 score=0.76 terms=cloud, data, etl, pipelines, warehouse
```

With `--out`, each stage writes a JSON artifact; one committed run lives in
[`examples/trace/`](examples/trace/). Your own inputs are described in
[`data/README.md`](data/README.md). Tests and lint: `pip install -r
requirements-dev.txt && pytest && ruff check .`

`--extractor llm` reads prose postings; `--matcher llm` grades coverage as
FULL, PARTIAL or GAP instead of the lexical binary. Both need a key and fail
immediately without one; the defaults never do. The full workflow — strategy,
practice questions, and a validated package — is the `prep` command, whose
strategy and question stages always call a provider:

```bash
export GEMINI_API_KEY=your-key
export GEMINI_MODEL=gemini-3.5-flash-lite   # optional

interview-prep-agent prep \
  --jd examples/sample_job_description.txt \
  --evidence examples/sample_evidence.yaml --out out/
```

`--evidence` also accepts a markdown resume (`.md`); its bullets become the
evidence corpus. Optional tracing: set `LANGSMITH_TRACING=true` plus a key to
trace provider calls and graph runs — traced runs upload inputs and outputs,
so use synthetic data, never a real posting or resume.

The decision loop is the `agent` command, same variables:

```bash
interview-prep-agent agent \
  --jd examples/sample_job_description.txt \
  --evidence examples/sample_evidence.yaml --out out/
```

The run pauses once per evidence gap with a focused factual question; each
answer is assessed and gate-checked, and only the admitted claim becomes
citable `CL-` evidence. `agent_trace.json` and `clarification_records.json`
record every selection, verdict and reason. Optionally describe the upcoming
round — it tailors strategy and questions, never matching:

```bash
interview-prep-agent agent --round "Technical screen with the data lead" \
  --jd examples/sample_job_description.txt \
  --evidence examples/sample_evidence.yaml --out out/
```

## Current state

Works today, covered by 124 tests:

* Requirement extraction from list-formatted postings, wording preserved
* Model-backed extraction and matching behind one provider seam, output
  schema-validated and gate-checked, never trusted raw
* Coverage grading (FULL / PARTIAL / GAP) with deterministic,
  importance-weighted focus areas ordering the preparation
* Strategy and practice-question generation, every reference held to the
  stable-identifier chain by the package gate
* Package validation routing failures to an error report — a run that fails
  its gate ends with errors listed and no package artifact
* The governed evidence loop (`agent`): every gap asked exactly once in a
  deterministic order, budgets from settings, routing in pure code
* Per-answer assessment behind a code-owned admission gate — admitted claims
  become citable `CL-` evidence, rejected answers stay in the audit trail
* Optional round context parsed once and threaded into preparation only,
  with `agent_trace.json` and `clarification_records.json` as the record
* Evidence from a YAML corpus or a markdown resume, identifiers minted once
  at the boundary
* Per-stage JSON artifacts, the `match`, `prep` and `agent` commands,
  settings from `--config`, then `IPA_CONFIG`, then the packaged default

Known limitations, in order of how much they cost:

* **Matching accuracy is unmeasured on both paths.** The default lexical
  matcher still scores "designed randomized experiments" at zero against "A/B
  testing" — false gaps remain its dominant error. The model matcher exists to
  close that, and its grounding is gate-checked, but whether its judgments are
  *right* has never been scored against labelled data. Neither path can honestly
  be called better yet; that claim needs the evaluation set, which is planned.
* **The agent loop is a capability, not a proven improvement.** It works and
  is gate-checked at every step, but nothing yet measures whether the
  packages it produces are better than a plain workflow run; that comparison
  needs the evaluation set, which is planned.
* **Round parsing and answer assessment are unmeasured model stages.** Both
  sit behind code-owned gates — a bad parse can only mis-emphasize, and a bad
  assessment can only reject or admit a claim the gates then bound — but
  whether their judgments are right is unscored, like every model stage here.
* **Model extraction is unmeasured.** Same shape: it reads prose the splitter
  cannot, its quotes are verified real, and its judgment is unscored.
* **The threshold is unvalidated.** `0.30` was set by inspecting one synthetic
  example, not by tuning against labelled data.
* **Accuracy is unmeasured.** The gates check structural integrity between
  stages. They cannot tell whether a verdict is correct.

## Design

Every claim traces to a source: requirements keep the posting's verbatim
wording, and every downstream object — match, focus area, strategy item,
question — cites by stable identifier, checked end to end by the package gate.
Both extraction paths face the same grounding gate and both matcher paths face
the same match gate; no path, deterministic or not, is exempt. Code owns
control flow: each branch is a pure predicate over a gate-computed boolean,
and a model only ever produces data that is then validated. The gates fail
loudly — output that violates a stated guarantee is not returned at all.

## Docs

[`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) — the layers, their interfaces,
ship criteria · [`docs/METHODOLOGY.md`](docs/METHODOLOGY.md) — extraction
paths, scoring formula, gates · [`docs/DECISIONS.md`](docs/DECISIONS.md) —
choices and their costs

References: Spärck Jones (1972) on term specificity; Robertson & Zaragoza
(2009) on BM25, deliberately not used — full citations in
[`docs/METHODOLOGY.md`](docs/METHODOLOGY.md).

MIT — see [LICENSE](LICENSE).
