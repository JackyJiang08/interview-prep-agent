# interview-prep-agent

[![CI](https://github.com/JackyJiang08/interview-prep-agent/actions/workflows/ci.yml/badge.svg)](https://github.com/JackyJiang08/interview-prep-agent/actions/workflows/ci.yml)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue)](pyproject.toml)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)

**Live demo:** https://interview-prep-agent.livelytree-f16ea3df.centralus.azurecontainerapps.io (no key needed, runs in the browser; sleeps when idle)

Paste a job posting and your resume, and the agent builds an interview
preparation package: which requirements you can back up, which you cannot,
and what to prepare for each. Where the posting exposes a gap, it asks you
one factual question, and only an answer that passes a check owned by code
becomes evidence. Every claim in the package cites the item that supports
it, so a wrong answer is a wrong link you can find and reject.

## What ships today

| Piece | What it does |
|---|---|
| [Deterministic workflow](docs/ARCHITECTURE.md#layer-1--deterministic-workflow--shipped) | Runs fixed stages on a graph; gates check grounding and traceability |
| [Model-backed extraction](docs/METHODOLOGY.md#stage-1---extraction) | Reads prose postings; validated, never raw; live defaults to it |
| Junk guard | Drops headings and disclaimers after extraction; records every drop |
| [Model-backed matching](docs/METHODOLOGY.md#stage-2---matching) | Grades coverage FULL / PARTIAL / GAP; live sessions default to it |
| Role research | Search and pasted notes become SRC- findings; never touch matching |
| [Preparation package](docs/METHODOLOGY.md#stages-3-5---assessment-strategy-questions) | Assesses gaps, writes strategy and questions; a gate routes failures |
| [Governed evidence loop](docs/ARCHITECTURE.md#layer-2--bounded-decision-layer--shipped) | Asks each gap once, skippable; a code-owned gate admits answers |
| Question ceiling | Caps a live run at six questions, most important first; overridable |
| [Regression evaluation](docs/METHODOLOGY.md#evaluation) | Scores trajectory, state and outcome on a scenario suite; red fails CI |
| [Three providers](docs/DECISIONS.md#what-the-second-provider-cost) | Serves Gemini, Azure OpenAI and Claude behind one seam |
| Web app | Reads PDF, markdown or YAML resumes; checks the evidence before a run |
| Progress and exports | Reports each stage while models run; Markdown export; clean print |
| [Deployment](docs/DEPLOYMENT.md) | Ships one CI-built container to Azure; scales to zero, wake absorbed |

**Roadmap.** Two things are planned and not built: durable state across runs
(a thread persists within one run; nothing carries between runs) and quality
evaluation against labelled data, without which no "is it better?" claim is
made. Both are described in [`ARCHITECTURE`](docs/ARCHITECTURE.md#layer-3--durable-state--planned).

## Try it

The live demo runs the sample with no key; your own posting needs a model
key, entered in the page and never stored. The same image, locally:

```bash
docker build -t interview-prep-agent . && docker run --rm -p 8000:8000 interview-prep-agent
```

The command line runs offline on the committed synthetic example:

```bash
git clone https://github.com/JackyJiang08/interview-prep-agent.git
cd interview-prep-agent
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

PYTHONPATH=src python -m interview_prep_agent.cli match \
  --jd examples/sample_job_description.txt \
  --evidence examples/sample_evidence.yaml --out out/
```

```
Coverage: 6 requirements | 3 PROOF | 3 GAP
[GAP ] REQ-002 Experience designing and interpreting A/B tests
        No evidence item covers this requirement. Prepare it first.
[PROOF] REQ-003 Build and maintain ETL pipelines in a cloud data warehouse
        - EV-002 score=0.76 terms=cloud, data, etl, pipelines, warehouse
```

`prep` runs the full workflow to a validated package; `agent` adds the
loop, pausing once per gap with a factual question. Both take `--provider
gemini|azure|anthropic` with the matching key in the environment. The
command line defaults to the lexical stages; `--extractor llm` reads prose
postings and `--matcher llm` grades coverage. `--evidence` takes a YAML
corpus or a markdown resume; `--round`, `--company`, `--role-title` and
`--research-file` reach preparation and research only, never matching.
With `--out`, each stage writes a JSON artifact, the guard's drops
included; one committed run lives in [`examples/trace/`](examples/trace/).
Tests, lint and the behavior matrix: `pip install -r requirements-dev.txt
-r requirements-server.txt && pytest && ruff check .` and
`interview-prep-agent eval --suite offline --local`; `web/` runs `npm test`.

## Current state

Works today, covered by 251 Python tests and 68 web tests:

* Requirement extraction from list-formatted postings, wording preserved
* Model-backed extraction and matching behind one provider seam, never trusted raw
* A guard after extraction: headings, disclaimers and fragments dropped, each drop recorded
* Coverage grading (FULL / PARTIAL / GAP) with importance-weighted focus areas
* Role research from targeted search and pasted notes; SRC- findings cited, never matched
* Strategy and question generation held to the identifier chain by the package gate
* Package validation routing failures to an error report, never a silent artifact
* The governed evidence loop: every gap asked once, budgets from settings, pure-code routing
* A code-owned admission gate; admitted claims become `CL-` evidence, rejections stay audit-only
* Skippable questions, recorded as unanswered; a live ceiling of six, most important first
* Live sessions word each question through the model, with the template as the fallback
* Round context parsed once, threaded into preparation only
* A behavioral regression suite, trajectory, state and outcome, run by CI; red fails the build
* A resume reader for real resumes: bullets, numbered lines, paragraphs, PDF text on the server
* Evidence checked before a run: the page reports the items read and refuses to start on none
* Staged progress while models run; Markdown export of the package and questions; print styles
* A web session layer over the same loop; the form survives a run, a failure and the way back
* Three providers, selectable on every surface; deployed as one container that scales to zero

Known limitations, in order of how much they cost:

* **Matching accuracy is unmeasured on both paths.** The lexical matcher,
  the default offline and in demos, still scores "designed randomized
  experiments" at zero against "A/B testing"; false gaps remain its dominant
  error. The model matcher, the default for live sessions, exists to close
  that, and its grounding is gate-checked, but whether its judgments are
  *right* has never been scored against labelled data. Neither path can honestly
  be called better yet; that claim needs the quality evaluation, which is planned.
* **The agent loop's quality is unmeasured.** Its trajectory and state behavior
  are regression-locked, so a silent change fails the build, but nothing yet
  measures whether the packages it produces are better than a plain workflow
  run; that comparison needs the quality evaluation, which is planned.
* **Round parsing and answer assessment are unmeasured model stages.** Both
  sit behind code-owned gates: a bad parse can only mis-emphasize, and a bad
  assessment can only reject or admit a claim the gates then bound. Whether
  their judgments are right is unscored, like every model stage here.
* **Model extraction is unmeasured.** Same shape: it reads prose the splitter
  cannot, its quotes are verified real, and its judgment is unscored. The
  guard behind it catches obvious junk, not a wrong requirement.
* **The threshold is unvalidated.** `0.30` was set by inspecting one synthetic
  example, not by tuning against labelled data.
* **Accuracy is unmeasured.** The gates check structural integrity between
  stages. They cannot tell whether a verdict is correct.

## Design

Every claim traces to a source: requirements keep the posting's verbatim
wording, and every downstream object cites by stable identifier, checked
end to end by the package gate. Both extraction paths face the same
grounding gate and both matcher paths the same match gate; no path is
exempt. Code owns control flow: each branch is a pure predicate over a
gate-computed boolean, and a model only ever produces data that is then
validated. The gates fail loudly: output that violates a stated guarantee
is not returned at all.

## Docs

[`ARCHITECTURE`](docs/ARCHITECTURE.md) (layers, interfaces, platform boundary)
· [`METHODOLOGY`](docs/METHODOLOGY.md) (extraction, scoring, gates, evaluation,
references) · [`DECISIONS`](docs/DECISIONS.md) (choices and their costs) ·
[`DEPLOYMENT`](docs/DEPLOYMENT.md) (container, Azure setup, deploy workflow) ·
[`FAILURE-ANALYSIS`](docs/FAILURE-ANALYSIS.md) (a deliberate regression, recorded)

MIT. See [LICENSE](LICENSE).
