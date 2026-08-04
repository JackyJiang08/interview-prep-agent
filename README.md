# interview-prep-agent

[![CI](https://github.com/JackyJiang08/interview-prep-agent/actions/workflows/ci.yml/badge.svg)](https://github.com/JackyJiang08/interview-prep-agent/actions/workflows/ci.yml)

A staged system for turning a job posting into a defensible interview
preparation plan — one where every claim traces back to something the candidate
can actually attest to, and each layer is only as autonomous as its decisions
require.

**Early prototype — active development.** Layer 1, the deterministic workflow,
is what runs today. The layers above it are described below and are not built.

## Problem

Preparing for a specific interview is a research task with a deadline. A posting
states a dozen requirements, the candidate has a body of real experience, and
somewhere in the gap between the two sits the small set of things actually worth
rehearsing. Finding that set takes more than one comparison: it means looking up
what the company ships, noticing which claims are thin, and revising after the
first conversation reveals what a panel really probes.

Handing all of that to a single model prompt fails in a specific way. The output
is fluent and contains claims that appear in neither the posting nor the
candidate's experience — an invented metric, a skill never demonstrated — and
gives no way to tell which part of the reasoning failed. It is unusable not
because it reads badly but because nothing in it can be checked.

This project treats that as a systems problem rather than a prompting one, along
two axes. Every claim carries a pointer to its source, so a wrong answer becomes
a wrong link that a reader can find and reject. And capability is added a layer
at a time, each layer no more autonomous than its own decisions require.

## Architecture

Four layers. Each is built only once its decisions justify the machinery it
needs, and each inherits the traceability guarantee of the ones below it. Full
reasoning and the interface between each pair:
[`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).

| Layer | Status | What it does |
|---|---|---|
| 1 — deterministic workflow | **shipped** | Extracts requirements, matches them to evidence, assembles a gap-first plan behind coverage and traceability gates. |
| 2 — bounded decision layer | **next** | Chooses among a small closed set of actions once tools and missing information make the next step a real decision. |
| 3 — durable state | **planned** | Carries a plan across turns so new information updates it instead of regenerating it. |
| Cross-cutting | **planned** | Execution traces, a labelled evaluation set, and written failure analysis. |

### Layer 1 — deterministic workflow · shipped

Requirement extraction, evidence matching, and gap-first plan assembly, guarded
by coverage and traceability gates. Fixed control flow, because these three
steps have no runtime branch to take.

Still open inside this layer: semantic matching, to close the lexical false-gap
problem noted under Known limitations; splitting bundled requirement lines into
atomic requirements; and calibrating `match_threshold` against labelled data
rather than by inspection.

### Layer 2 — bounded decision layer · next

Once the system can call tools and act on missing information, "what to do next"
becomes a real decision rather than a fixed sequence. This layer chooses among a
small, closed set of actions — request evidence, research, revise, stop — under
a step limit, recording which action it took and why.

Ships once there is at least one real tool with a defined failure mode,
execution traces good enough to debug a wrong trajectory, and an evaluation set
showing the loop does not degrade what Layer 1 already gets right.

### Layer 3 — durable state · planned

State that survives across turns, so research results and post-interview
feedback update an existing plan instead of regenerating it. Regeneration is the
wrong default: it discards work the candidate has already reviewed and makes
successive versions incomparable.

Ships once the state has a versioned schema, updates are idempotent, and there
is a defined rule for what a newly learned fact may overwrite.

### Cross-cutting — traces, evaluation, failure analysis · planned

Execution traces spanning every layer, a labelled evaluation set of real
postings scoring false gaps and false proofs separately, and written failure
analysis. The evaluation set gates most of the work above: without it there is
no way to tell an improvement from a change.

## Approach

* **Autonomy proportional to the decision.** A loop is not justified where there
  is no decision to make. Layer 1's three stages have none — extraction always
  precedes matching, matching always precedes assembly, and no result can change
  what runs next — so its control flow is fixed in code. That is a claim about
  these three steps, not an argument against agency. Real decisions appear the
  moment the system meets the world: which missing evidence to ask the candidate
  for, what to do when a research tool returns thin results or fails outright,
  and how to revise a plan after interview feedback contradicts it. Those three
  points are Layer 2, and that is where a loop earns its cost.
* **Verbatim grounding.** Requirements keep the posting's exact wording. A
  separate normalized form exists for comparison and is never displayed.
* **Transparent scoring.** Requirements are matched to evidence by
  IDF-weighted term overlap, scored as the share of a requirement's weighted
  terms that the evidence attests. Every match reports the terms that produced
  it, so a verdict can be read rather than guessed at.
* **Gates that raise.** Coverage (no requirement dropped or invented) and
  traceability (no citation to evidence that does not exist) are checked before
  a plan is returned, and fail loudly rather than degrading.
* **Attributable failure.** Each stage writes its own JSON artifact, so a bad
  plan can be traced to the stage that produced the bad input.

## Repo structure

```
interview-prep-agent/
├── src/interview_prep_agent/
│   ├── workflow/       the deterministic layer
│   │   ├── extract.py    stage 1 — posting text to atomic requirements
│   │   ├── match.py      stage 2 — IDF-weighted lexical scoring
│   │   ├── plan.py       stage 3 — gap-first assembly and quality gates
│   │   └── pipeline.py   orchestration and per-stage artifacts
│   ├── models.py       validated contracts shared across stage boundaries
│   ├── corpus.py       reading postings and evidence from disk
│   ├── config.py       settings resolution
│   └── cli.py          command-line entry point
├── tests/              per-stage smoke tests plus end-to-end
├── examples/           synthetic posting and evidence corpus
│   └── trace/          per-stage artifacts from one committed run
├── configs/            tunables, no hardcoded paths
├── data/               where your own inputs go, not committed
└── docs/
    ├── ARCHITECTURE.md the four layers, their interfaces, and ship criteria
    ├── METHODOLOGY.md  scoring formula, gates, and limitations
    └── DECISIONS.md    choices made and the reasoning behind them
```

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

Runs on the committed synthetic example with no configuration and no network
access. Output:

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

With `--out`, each stage writes its own JSON artifact. A run over the committed
example is checked in under [`examples/trace/`](examples/trace/), so the stage
boundaries can be read without installing anything: a verdict in
`focus_plan.json` traces back to a score in `matches.json`, to the terms that
produced it, to a source line in `requirements.json`.

Installing the package provides a console command instead:

```bash
pip install -e .
interview-prep-agent match --jd examples/sample_job_description.txt \
                           --evidence examples/sample_evidence.yaml --out out/
```

Tests and lint, the same checks CI runs:

```bash
pip install -r requirements-dev.txt
pytest
ruff check . && ruff format --check .
```

### Your own inputs

A posting is plain text, one requirement per line. An evidence corpus is YAML:

```yaml
- id: EV-001
  summary: Owned funnel analysis for a subscription product, in SQL and Python.
  skills: [sql, python, funnel analysis]
  impact: Reduced a weekly reporting cycle from two days to under an hour.
```

Both stay local; `data/` is not committed. See [`data/README.md`](data/README.md).

## Current state

Works today, covered by 20 tests:

* Requirement extraction from list-formatted postings, wording preserved
* IDF-weighted lexical matching with per-match term attribution
* Gap-first plan assembly with coverage and traceability gates
* Per-stage JSON artifacts and a command-line interface
* Settings resolved from `--config`, then `IPA_CONFIG`, then the packaged default

Known limitations, in order of how much they cost:

* **Matching is lexical.** "Designed randomized experiments" scores zero against
  "A/B testing" — no shared terms. False gaps are the dominant error mode.
* **Extraction is line-based.** A line bundling three requirements stays one
  requirement. Postings written as prose fall back to a weaker path that admits
  sentences stating no requirement.
* **The threshold is unvalidated.** `0.30` was set by inspecting one synthetic
  example, not by tuning against labelled data.
* **Accuracy is unmeasured.** The gates check structural integrity between
  stages. They cannot tell whether a verdict is correct.

## References

Layer breakdown and interfaces: [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).
Method, scoring formula and citations: [`docs/METHODOLOGY.md`](docs/METHODOLOGY.md).
Choices made and why: [`docs/DECISIONS.md`](docs/DECISIONS.md).

* Spärck Jones, K. (1972). *A statistical interpretation of term specificity and
  its application in retrieval.* Journal of Documentation, 28(1), 11–21.
* Robertson, S. & Zaragoza, H. (2009). *The Probabilistic Relevance Framework:
  BM25 and Beyond.* Foundations and Trends in Information Retrieval, 3(4), 333–389.

## License

MIT — see [LICENSE](LICENSE).
