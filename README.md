# jd-evidence-matcher

Match the stated requirements of a job description against a corpus of attested
experience, and label each requirement as proven or unproven with a citation.

**Early prototype — active development**

## Problem

A job posting states a dozen requirements. A candidate has a body of real
experience. Deciding which requirements the experience actually covers is
tedious to do by hand and unreliable to do with a single model prompt.

The unreliability has a specific shape. Asked to do the whole job in one step, a
language model returns fluent output containing claims that appear in neither the
posting nor the experience — an invented metric, a skill never demonstrated — and
gives no way to tell which part of the reasoning failed. The output is unusable
not because it reads badly but because nothing in it can be checked.

This project treats that as a systems problem rather than a prompting one. If
every stage boundary is validated and every claim carries a pointer to its
source, a wrong answer becomes a wrong link that a reader can find and reject.

## Approach

* **Fixed control flow.** Three stages run in the same order on every
  invocation. Nothing decides at runtime what to do next, because none of the
  three steps has a real branch to make.
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
jd-evidence-matcher/
├── src/jd_evidence_matcher/
│   ├── models.py       validated contracts shared across stage boundaries
│   ├── extract.py      stage 1 — posting text to atomic requirements
│   ├── match.py        stage 2 — IDF-weighted lexical scoring
│   ├── plan.py         stage 3 — gap-first assembly and quality gates
│   ├── pipeline.py     orchestration and per-stage artifacts
│   ├── corpus.py       reading postings and evidence from disk
│   ├── config.py       settings resolution
│   └── cli.py          command-line entry point
├── tests/              per-stage smoke tests plus end-to-end
├── examples/           synthetic posting and evidence corpus
├── configs/            tunables, no hardcoded paths
├── data/               local inputs, not committed
├── docs/METHODOLOGY.md scoring formula, gates, and limitations
└── notebooks/          exploratory work
```

## Quickstart

```bash
git clone https://github.com/JackyJiang08/jd-evidence-matcher.git
cd jd-evidence-matcher
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

PYTHONPATH=src python -m jd_evidence_matcher.cli \
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

Installing the package provides a console command instead:

```bash
pip install -e .
jd-evidence-matcher --jd examples/sample_job_description.txt \
                    --evidence examples/sample_evidence.yaml --out out/
```

Tests:

```bash
pip install -r requirements-dev.txt && pytest
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
* Settings resolved from `--config`, then `JDEM_CONFIG`, then the packaged default

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

## Roadmap

1. **Labelled evaluation set** — real postings with hand-labelled verdicts,
   scoring false-gap and false-proof rates separately, since a false gap wastes
   preparation time while a false proof leaves a real weakness unaddressed.
   Everything below is unmeasurable without this.
2. **Semantic matching** — embedding or model-backed scoring behind the existing
   matcher seam, to close the lexical false-gap problem. Provider-agnostic.
3. **Requirement splitting** — decompose bundled lines into atomic requirements.
4. **Threshold calibration** — set `match_threshold` from the evaluation set
   rather than by inspection.
5. **Bounded interactive step** — request missing evidence where the corpus is
   thin. Stages 1–3 stay fixed in code; a loop buys nothing where there is no
   decision to make.

## References

Method, scoring formula and citations: [`docs/METHODOLOGY.md`](docs/METHODOLOGY.md).

* Spärck Jones, K. (1972). *A statistical interpretation of term specificity and
  its application in retrieval.* Journal of Documentation, 28(1), 11–21.
* Robertson, S. & Zaragoza, H. (2009). *The Probabilistic Relevance Framework:
  BM25 and Beyond.* Foundations and Trends in Information Retrieval, 3(4), 333–389.

## License

MIT — see [LICENSE](LICENSE).
