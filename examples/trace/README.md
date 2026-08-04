# Example trace

The per-stage artifacts from one run over the committed synthetic inputs
(`sample_job_description.txt` and `sample_evidence.yaml`), checked in so the
stage boundaries can be read without installing anything.

| File | Stage | What it shows |
|---|---|---|
| `requirements.json` | 1 — extraction | Each requirement with the posting's exact wording, its normalized comparison form, and the source line it came from. |
| `matches.json` | 2 — scoring | One verdict per requirement, with the evidence cited, the score, and the overlapping terms that produced it. |
| `focus_plan.json` | 3 — assembly | The final gap-first plan and the coverage totals. |

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
