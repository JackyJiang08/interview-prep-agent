# Data

Nothing in this directory is committed except this file and `raw/.gitkeep`.
Postings and evidence corpora are personal, so they stay on the machine that
produced them.

## Layout

```
data/
├── raw/        job descriptions as plain text, and evidence corpora
└── README.md
```

## Where the inputs come from

**Job descriptions.** Copy the posting into a plain-text file, one requirement
per line. Keep the wording exactly as published: the grounding gate compares
output against this text, so paraphrasing here silently weakens the guarantee.
Postings are the property of whoever published them; keep them local.

    data/raw/<company>-<role>.txt

**Evidence corpora.** You write these by hand. Each entry is one thing you can
actually attest to, with a stable identifier that the plan will cite.

    data/raw/evidence.yaml

```yaml
- id: EV-001
  summary: One or two sentences on what you did.
  skills: [sql, python]
  impact: The measurable outcome, if there was one.
```

Identifiers must be unique and should stay stable across edits, since older
artifacts in `out/` refer to them.

## Sample inputs

`examples/` holds a synthetic posting and a synthetic corpus that the quickstart
and the tests run against. They are invented and describe no real person, which
is why they are safe to commit. Use them to check that a change still works
before pointing the pipeline at anything real.
