# Example trace

The per-stage artifacts from one run over the committed synthetic inputs
(`sample_job_description.txt` and `sample_evidence.yaml`), checked in so the
stage boundaries can be read without installing anything.

| File | Stage | What it shows |
|---|---|---|
| `requirements.json` | 1 — extraction | Each requirement with the posting's exact wording, its normalized comparison form, the `source_quote` that grounds it in the posting, and the source line it came from. |
| `matches.json` | 2 — matching | One verdict per requirement: the evidence cited with its score and overlapping terms, the coverage level (`FULL`/`GAP` on this lexical run — the lexical matcher never claims `PARTIAL`), an explanation, and a confidence. |
| `focus_areas.json` | 2b — assessment | Every requirement ranked by `importance × coverage weight`, with the fixed preparation action for its coverage level and the matcher's explanation as the reason. |
| `focus_plan.json` | 3 — assembly | The final plan in focus-area order and the coverage totals. |

This run used the default lexical extractor and matcher, so each
`source_quote` equals the extracted text, fields only the model-backed paths
can supply (category, importance, requirement type) are absent — the artifacts
omit unset fields rather than writing null — and with no importance data the
focus ordering reduces to gaps first in source order.

A `prep` run writes three further artifacts — `strategy.json`,
`questions.json`, and `prep_package.json` when the package gate passes — and
an `agent` run adds `agent_trace.json`, the ordered record of every
observation, proposal, authorization verdict and stop reason from the
decision loop. Neither has a committed run: those stages call a provider, and
a committed artifact must be a deterministic function of the repo, which a
model response is not.

Reading them in order is the argument for the design: a wrong verdict in
`focus_plan.json` can be traced back to a specific score in `matches.json`, and
from there to the terms that produced the score, and from there to the source
line in `requirements.json`. Nothing needs to be re-derived from a model.

Regenerate with:

```bash
interview-prep-agent match \
  --jd examples/sample_job_description.txt \
  --evidence examples/sample_evidence.yaml \
  --out examples/trace/
```

Committed output normally belongs nowhere near version control. The exception
holds here because the inputs are synthetic and committed, so these files are a
deterministic function of the repo and change only when behaviour changes,
which makes an unexpected diff a signal rather than noise.
