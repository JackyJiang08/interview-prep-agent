# interview-prep-agent

[![CI](https://github.com/JackyJiang08/interview-prep-agent/actions/workflows/ci.yml/badge.svg)](https://github.com/JackyJiang08/interview-prep-agent/actions/workflows/ci.yml)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue)](pyproject.toml)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)

**Live demo:** https://interview-prep-agent.livelytree-f16ea3df.centralus.azurecontainerapps.io (no key needed, runs in the browser; sleeps when idle)

![The preparation package, every claim citing its evidence](docs/assets/package-view.png)

Paste a job posting and your resume, and the agent builds an interview
preparation package: which requirements you can back up, which you cannot,
and what to prepare for each. Where the posting exposes a gap, it asks you
one factual question, and only an answer that passes a check owned by code
becomes evidence. Every claim in the package cites the item that supports
it, so a wrong answer is a wrong link you can find and reject.

## What ships today

| Piece | What it does |
|---|---|
| [Deterministic workflow](docs/ARCHITECTURE.md#layer-1--deterministic-workflow--shipped) | Fixed stages on a graph runtime; grounding and traceability gates between them |
| [Model-backed extraction](docs/METHODOLOGY.md#stage-1---extraction) | Reads prose postings behind a provider seam; output validated, never trusted raw |
| [Model-backed matching](docs/METHODOLOGY.md#stage-2---matching) | FULL / PARTIAL / GAP coverage per requirement; the lexical matcher stays the default |
| [Preparation package](docs/METHODOLOGY.md#stages-3-5---assessment-strategy-questions) | Gap assessment, strategy, practice questions; a package gate routes failures to an error report |
| [Governed evidence loop](docs/ARCHITECTURE.md#layer-2--bounded-decision-layer--shipped) | Every gap asked once; a code-owned admission gate; rejected answers stay audit-only |
| [Regression evaluation](docs/METHODOLOGY.md#evaluation) | Scenario suite scoring trajectory, state and outcome; red fails the build |
| Three model providers | Gemini, Azure OpenAI and Claude behind one seam; [what each one cost](docs/DECISIONS.md#what-the-second-provider-cost) |
| Web app | Session layer over the same loop; resume intake as markdown, YAML or PDF; evidence checked before a run |
| [Deployment](docs/DEPLOYMENT.md) | One container, built in CI, on Azure Container Apps; scales to zero, the page absorbs the wake |

**Roadmap.** Two things are stated as planned and are not built. Durable
state across runs: a resumed thread already persists within one run, but
nothing carries what was learned from one run to the next. Quality
evaluation against labelled data: nothing yet scores match verdicts or
package quality against hand-labelled references, and until it exists no
"is it better?" claim is made here. Both are described honestly in
[`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md#layer-3--durable-state--planned).

## Try it

The live demo runs the sample with no key. Your own posting and resume
need a model key for Gemini, Azure OpenAI or Claude, entered in the page
and never stored. To run the same image locally:

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
loop, pausing once per gap with a factual question. Both take
`--provider gemini|azure|anthropic` and the matching key in the
environment (`GEMINI_API_KEY`, the `AZURE_OPENAI_*` settings, or
`ANTHROPIC_API_KEY`). `--extractor llm` reads prose postings; `--matcher
llm` grades coverage; `--evidence` takes a YAML corpus or a markdown
resume; `--round` tailors strategy and questions, never matching. With
`--out`, each stage writes a JSON artifact; one committed run lives in
[`examples/trace/`](examples/trace/). Tests, lint and the behavior matrix:
`pip install -r requirements-dev.txt -r requirements-server.txt && pytest
&& ruff check .` and `interview-prep-agent eval --suite offline --local`;
the web app under `web/` runs `npm test`.

## Current state

Works today, covered by 220 Python tests and 55 web tests:

* Requirement extraction from list-formatted postings, wording preserved
* Model-backed extraction and matching behind one provider seam, never trusted raw
* Coverage grading (FULL / PARTIAL / GAP) with importance-weighted focus areas
* Strategy and question generation held to the identifier chain by the package gate
* Package validation routing failures to an error report, never a silent artifact
* The governed evidence loop: every gap asked once, budgets from settings, pure-code routing
* A code-owned admission gate; admitted claims become `CL-` evidence, rejections stay audit-only
* Round context parsed once, threaded into preparation only
* A behavioral regression suite, trajectory, state and outcome, run by CI; red fails the build
* A resume reader for real resumes: bullets, numbered lines, paragraphs under headings, bare paragraphs; PDF text extracted on the server and shown for correction
* Evidence checked before a run: the page reports how many items were read and refuses to start on none
* A web session layer over the same loop; the form survives a run, a failure and the way back
* Three providers, selectable on every surface; deployed as one container that scales to zero

Known limitations, in order of how much they cost:

* **Matching accuracy is unmeasured on both paths.** The default lexical
  matcher still scores "designed randomized experiments" at zero against "A/B
  testing"; false gaps remain its dominant error. The model matcher exists to
  close that, and its grounding is gate-checked, but whether its judgments are
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
  cannot, its quotes are verified real, and its judgment is unscored.
* **The threshold is unvalidated.** `0.30` was set by inspecting one synthetic
  example, not by tuning against labelled data.
* **Accuracy is unmeasured.** The gates check structural integrity between
  stages. They cannot tell whether a verdict is correct.

## Design

Every claim traces to a source: requirements keep the posting's verbatim
wording, and every downstream object, whether match, focus area, strategy
item or question, cites by stable identifier, checked end to end by the
package gate. Both extraction paths face the same grounding gate and both
matcher paths face the same match gate; no path, deterministic or not, is
exempt. Code owns control flow: each branch is a pure predicate over a
gate-computed boolean, and a model only ever produces data that is then
validated. The gates fail loudly: output that violates a stated guarantee
is not returned at all.

## Docs

[`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) (the layers, their
interfaces, ship criteria, where the platform begins) ·
[`docs/METHODOLOGY.md`](docs/METHODOLOGY.md) (extraction paths, scoring
formula, gates, evaluation) · [`docs/DECISIONS.md`](docs/DECISIONS.md)
(choices and their costs, three providers in) ·
[`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md) (the container, the one-time
Azure setup, the deploy workflow) ·
[`docs/FAILURE-ANALYSIS.md`](docs/FAILURE-ANALYSIS.md) (a deliberate
regression, caught and recorded)

References: Spärck Jones (1972) on term specificity; Robertson & Zaragoza
(2009) on BM25, deliberately not used; full citations in
[`docs/METHODOLOGY.md`](docs/METHODOLOGY.md).

MIT. See [LICENSE](LICENSE).
