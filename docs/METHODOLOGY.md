# Methodology

How the pipeline decides that a requirement is supported, and what that decision
is and is not worth.

## Problem

Given a job posting and a corpus of things a candidate can attest to, decide for
each stated requirement whether the corpus supports it. The output is only useful
if it is *traceable*: a requirement marked as supported has to name the evidence
that supports it, so a reader can disagree with a specific link rather than with
the system as a whole.

The failure this design targets is a specific one. A single large prompt asked to
do the whole task in one step produces fluent output containing claims that
appear in neither the posting nor the corpus, and offers no way to localize which
part of the reasoning went wrong. Splitting the task into stages with validated
boundaries does not make the model smarter; it makes the error attributable.

## Design

Control flow is fixed in code and runs on a state graph. Every invocation
follows the same shape: extract, validate the extraction, then either match and
plan, or report the validation errors and stop. This is a workflow in the sense
of Anthropic's taxonomy [3] — the path is predetermined, not chosen at runtime.
The one conditional edge does not change that: both targets are wired when the
graph is built, and the routing predicate is a pure function of a boolean that
deterministic gate code computed. A model, when one is used, produces data that
is then validated; it never chooses the next node.

### Stage 1 - extraction

Input is the posting as plain text; output is a list of `Requirement` records.
There are two implementations, selected with `--extractor`; both emit the same
model and both are held to the same grounding gate described below.

**Lexical path** (`lexical`, the default). Postings state their requirements as
a list far more often than not, so a leading list marker is the signal. Lines
carrying one become candidates, headings such as "Requirements" or "About the
role" are dropped, and lines shorter than eight characters are discarded as
noise. When a posting contains no list at all, the stage falls back to treating
every non-heading line as a candidate.

Each record keeps the source wording verbatim after marker removal, plus a
lowercased, whitespace-collapsed `normalized` form used only for deduplication.
Nothing downstream may display `normalized`; the plan quotes `text`. The
record's `source_quote` is the extracted span itself — a lexically extracted
requirement is by construction a substring of the posting, and stating that
explicitly is what lets one gate serve both paths.

The fallback is the weak point. On a posting written as prose paragraphs it
admits sentences that state no requirement, and it cannot split a line that
bundles three requirements into one. Both are visible in the output rather than
hidden, which is the most that can be claimed for them.

**Model-backed path** (`llm`). A provider is asked for requirements as
structured JSON, and its answer passes through three layers before anything
downstream sees it:

1. *The model proposes.* The prompt states constraints, not encouragement:
   copy `source_quote` character for character, assign sequential identifiers,
   take nothing that is not in the text. Every rule in the prompt has a
   matching deterministic check, because a rule the code cannot verify is a
   hope rather than a constraint.
2. *The schema validates structure.* The response is validated against the
   same Pydantic `Requirement` model the lexical path produces — field types,
   identifier format, the importance scale, the category set — and additionally
   for the fields only this path can supply. A malformed or over-full response
   raises; nothing is salvaged from it.
3. *The gates verify grounding.* Every `source_quote` must appear in the
   posting (compared whitespace- and case-insensitively, nothing else
   forgiven), identifiers must run sequentially from REQ-001, statements must
   not repeat, and the count must fall inside configured bounds.

The division of labour is the point: the model is used for what it is good at —
reading prose — and is never the authority on whether its own output is
grounded. A response citing text that is not in the posting fails the run
exactly as a bug in the lexical splitter would.

The model call itself sits behind a provider seam: stages depend on an abstract
contract (prompt and JSON schema in, parsed response out), and the first
implementation is Gemini. No stage imports a vendor SDK.

### Stage 2 - scoring

Input is the requirements and the evidence corpus; output is one verdict per
requirement.

Terms are lowercased and tokenized, dropping stopwords and single characters.
Compound terms are kept whole *and* split, so `SQL/Python` contributes
`sql/python`, `sql` and `python`, while `A/B` survives as a term its
one-character parts could not represent.

Each term is weighted by inverse document frequency over the evidence corpus,
following the standard term-specificity argument [1]: a term appearing in every
evidence item distinguishes nothing, and a rare term carries most of the signal.

    weight(t) = log(1 + N / (1 + df(t)))

where `N` is the number of evidence items and `df(t)` how many contain `t`. Terms
absent from the corpus take `log(1 + N)`, the weight a maximally rare term would
have, so a requirement full of unattested jargon scores low rather than being
silently ignored.

The score of requirement `r` against evidence item `e` is the share of `r`'s
weighted terms that `e` attests:

    score(r, e) = Σ weight(t) for t in terms(r) ∩ terms(e)
                  ─────────────────────────────────────────
                        Σ weight(t) for t in terms(r)

This lands in [0, 1] and reads directly as "how much of this requirement is
actually backed up". A requirement scoring at or above `match_threshold`
(default 0.30) against at least one item is `PROOF`; otherwise `GAP`. Every match
reports the overlapping terms that produced it.

This is deliberately not BM25 [2]. BM25's saturation and length-normalization
terms are tuned for ranking documents by relevance to a short query; here the
quantity of interest is coverage of the *query* side, and the corpus is a few
dozen short items rather than a large collection. The simpler formula is also
readable off the output, which matters more at this stage than ranking quality.

The honest limitation: this is lexical matching. It scores "designed randomized
experiments" against "A/B testing" at zero, because they share no terms. That is
a false gap, and it is the single largest source of error in the current
baseline. Denser matching is the first roadmap item.

### Stage 3 - planning and gates

Verdicts are assembled into a plan ordered gaps-first, preserving source order
within each group. Three checks run before the plan is returned, and each raises
rather than degrading quietly:

* **Coverage** — the set of requirement identifiers going in equals the set
  coming out. Catches a requirement dropped or invented between stages.
* **Traceability** — every cited evidence identifier exists in the corpus, and
  nothing is marked `PROOF` without at least one citation.
* **Grounding** — displayed text is carried by reference from the extraction
  stage, so it cannot drift. `tests/test_extract.py` asserts every extracted
  requirement appears verbatim in the source.

These are cheap assertions, not a guarantee of correctness. They catch structural
breakage between stages. They cannot catch a match that is structurally valid and
semantically wrong — only a threshold change or a better matcher does that.

## Evaluation

There is none yet, beyond the smoke tests. Reporting a coverage number over a
single synthetic posting would say nothing about accuracy on real ones. A useful
evaluation needs a set of real postings with hand-labelled PROOF/GAP verdicts,
scored on false-gap and false-proof rate separately, since the two costs are not
symmetric: a false gap wastes preparation time, while a false proof leaves a real
weakness unprepared. Building that set is a roadmap item.

## References

1. Spärck Jones, K. (1972). *A statistical interpretation of term specificity and
   its application in retrieval.* Journal of Documentation, 28(1), 11–21. —
   origin of the inverse-document-frequency weighting used in stage 2.
2. Robertson, S. & Zaragoza, H. (2009). *The Probabilistic Relevance Framework:
   BM25 and Beyond.* Foundations and Trends in Information Retrieval, 3(4),
   333–389. — the ranking function this design deliberately does not use, and why.
3. Anthropic (2024). *Building Effective Agents.*
   https://www.anthropic.com/engineering/building-effective-agents — the
   workflow-versus-agent distinction that motivates fixing control flow in code.
4. Pydantic documentation. https://docs.pydantic.dev/ — the validation layer
   enforcing the stage contracts in `src/interview_prep_agent/models.py`.
