# interview-prep-agent

[![CI](https://github.com/JackyJiang08/interview-prep-agent/actions/workflows/ci.yml/badge.svg)](https://github.com/JackyJiang08/interview-prep-agent/actions/workflows/ci.yml)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue)](pyproject.toml)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)

Turns a job posting plus a corpus of attested experience into a gap-first
interview preparation plan. Every claim in the plan cites the source that
justifies it, so a wrong answer is a wrong link a reader can find and reject.
Built in stages, each only as autonomous as its decisions require.

## Status

| Stage | Status |
|---|---|
| [Deterministic workflow](docs/ARCHITECTURE.md#layer-1--deterministic-workflow--shipped) — graph runtime, grounding and traceability gates | **shipped** |
| [Model-backed extraction](docs/METHODOLOGY.md#stage-1---extraction) — behind a provider seam, output never trusted raw | **shipped** |
| [Bounded decision layer](docs/ARCHITECTURE.md#layer-2--bounded-decision-layer--next) — a closed action set once tools make "what next" a real decision | next |
| [Durable state](docs/ARCHITECTURE.md#layer-3--durable-state--planned) — new information updates a plan instead of regenerating it | planned |
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
Method: lexical-idf-v1

[GAP ] REQ-002 Experience designing and interpreting A/B tests
        No evidence item covers this requirement. Prepare it first.
...
[PROOF] REQ-003 Build and maintain ETL pipelines in a cloud data warehouse
        Supported by EV-002.
        - EV-002 score=0.76 terms=cloud, data, etl, pipelines, warehouse
```

With `--out`, each stage writes a JSON artifact; one committed run lives in
[`examples/trace/`](examples/trace/). Your own inputs are described in
[`data/README.md`](data/README.md). Tests and lint: `pip install -r
requirements-dev.txt && pytest && ruff check .`

To read prose postings, switch extraction to a model:

```bash
export GEMINI_API_KEY=your-key
export GEMINI_MODEL=gemini-3.5-flash-lite   # optional

interview-prep-agent match --extractor llm \
  --jd examples/sample_job_description.txt \
  --evidence examples/sample_evidence.yaml --out out/
```

Without a key this mode fails immediately with an actionable message; the
default lexical extractor never needs one.

## Current state

Works today, covered by 46 tests:

* Requirement extraction from list-formatted postings, wording preserved
* Model-backed extraction behind a provider seam (`--extractor llm`), its output
  schema-validated and grounding-checked, never trusted raw
* The workflow on a graph runtime, with one code-owned conditional edge routing
  invalid extraction to an error report instead of onward
* IDF-weighted lexical matching with per-match term attribution
* Gap-first plan assembly with coverage and traceability gates
* Per-stage JSON artifacts and a command-line interface
* Settings resolved from `--config`, then `IPA_CONFIG`, then the packaged default

Known limitations, in order of how much they cost:

* **Matching is lexical.** "Designed randomized experiments" scores zero against
  "A/B testing" — no shared terms. False gaps are the dominant error mode.
* **Model extraction is unmeasured.** The llm path reads prose postings the
  lexical splitter cannot, and its grounding is verified — but whether it finds
  the *right* requirements has never been scored against labelled data. The
  gates prove its quotes are real, not that its judgment is good.
* **The threshold is unvalidated.** `0.30` was set by inspecting one synthetic
  example, not by tuning against labelled data.
* **Accuracy is unmeasured.** The gates check structural integrity between
  stages. They cannot tell whether a verdict is correct.

## Design

Every claim traces to a source: requirements keep the posting's verbatim
wording, and matches cite evidence by stable identifier. Both extraction paths
— lexical and model-backed — face the same grounding gate, so no extractor is
exempt from proving its output against the posting. Code owns control flow: the
graph's one branch is a pure predicate over a gate-computed boolean, and a
model only ever produces data that is then validated. The gates fail loudly —
a plan that violates a stated guarantee is not returned at all.

## Docs

[`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) — the layers, their interfaces,
ship criteria · [`docs/METHODOLOGY.md`](docs/METHODOLOGY.md) — extraction
paths, scoring formula, gates · [`docs/DECISIONS.md`](docs/DECISIONS.md) —
choices and their costs

References: Spärck Jones (1972) on term specificity; Robertson & Zaragoza
(2009) on BM25, deliberately not used — full citations in
[`docs/METHODOLOGY.md`](docs/METHODOLOGY.md).

MIT — see [LICENSE](LICENSE).
