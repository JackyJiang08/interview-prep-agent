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

Control flow is fixed in code and runs on state graphs — a short one behind
`match` (extract, validate, then match and plan or report errors) and the full
one behind `prep` (inputs, evidence, extraction, matching, assessment,
strategy, questions, then package validation into assembly or an error
report). Both are workflows in the sense of Anthropic's taxonomy [3] — the
path is predetermined, not chosen at runtime. The conditional edges do not
change that: every branch target is wired when the graph is built, and each
routing predicate is a pure function of a boolean that deterministic gate code
computed. A model, where one is used, produces data that is then validated; it
never chooses the next node, and it never approves its own output.

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

### Stage 2 - matching

Input is the requirements and the evidence corpus; output is one verdict per
requirement, graded on a three-level coverage scale:

* **FULL** — supplied evidence directly supports every important part of the
  requirement.
* **PARTIAL** — related supplied evidence exists but misses an important
  dimension.
* **GAP** — no supplied evidence supports the requirement. A gap is a correct
  and useful answer, kept visible rather than papered over.

The older binary status survives as the degenerate view: anything but a gap is
proof. Two matcher implementations produce the same verdict model, and both
face the same deterministic match gate — every requirement judged exactly
once, in order; every citation resolving; a gap citing nothing; anything else
citing at least one item.

**Lexical path** (`--matcher lexical`, the default). Terms are lowercased and
tokenized, dropping stopwords and single characters.
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
(default 0.30) against at least one item is `FULL`; otherwise `GAP`. The
lexical path never emits `PARTIAL`, and the restraint is deliberate: term
overlap can measure how much of a requirement's vocabulary the evidence
attests, but it cannot recognise that the unattested part is an important
*dimension* — that takes reading. Claiming `PARTIAL` from a middling score
would dress that ignorance up as a judgment. Confidence is the top evidence
score, unchanged, and every match reports the overlapping terms that produced
it.

This is deliberately not BM25 [2]. BM25's saturation and length-normalization
terms are tuned for ranking documents by relevance to a short query; here the
quantity of interest is coverage of the *query* side, and the corpus is a few
dozen short items rather than a large collection. The simpler formula is also
readable off the output, which matters more at this stage than ranking quality.

The honest limitation: this is lexical matching. It scores "designed randomized
experiments" against "A/B testing" at zero, because they share no terms. That
is a false gap, and it is the dominant error of this path.

**Model-backed path** (`--matcher llm`). One structured-output call through the
provider seam: requirements and evidence in, one assessment per requirement out
— coverage, cited evidence identifiers, an explanation, and a confidence in
[0, 1]. Because this path reads, it may say `PARTIAL` and name the missing
dimension. The prompt states that only supplied identifiers may be referenced,
that missing support must be returned as `GAP`, and that invention is the
failure mode; the response is schema-validated, converted to the same verdict
model, and held to the same match gate as the lexical path. Whether its
judgments are *right* is unmeasured — the gate proves its citations are real,
not that its reading is good — so neither path can honestly be called better
until the evaluation set exists.

### Stages 3-5 - assessment, strategy, questions

**Gap assessment** is deterministic arithmetic, not judgment. Each requirement
becomes a focus area with

    focus_priority = importance × coverage_weight   (FULL 1, PARTIAL 2, GAP 3)

sorted descending, ties in source order, so a gap on a critical requirement
lands first and a covered nice-to-have lands last. The action is fixed per
coverage level and the reason carries the matcher's explanation. When a
requirement has no importance — the lexical extractor cannot supply one — the
neutral weight 1 is used and the ordering degrades to coverage alone, which is
exactly the older gap-first rule.

**Strategy and questions** are the two remaining model stages, both through
the same seam: a strategy (priorities, positioning, stories, risks) composed
from the focus areas, then eight to twelve practice questions grounded in it.
Each response is schema-validated; every deterministic judgment about it
belongs to the gates.

### The package gate

Before a package is assembled, one collected invariant set runs end to end,
and its outcome routes the graph — a valid run assembles the package, an
invalid one ends with its errors listed and no package artifact:

* every section present — evidence, requirements, matches, focus areas,
  strategy, and at least eight questions
* the extraction and match gates re-checked over the final state
* every requirement carrying an explicit coverage level, with exactly one
  focus area agreeing with it
* every downstream reference — strategy item, story, risk, question —
  resolving to a real requirement, citing only evidence already matched to
  that requirement, and citing nothing when the requirement is a gap
* every gap focus area appearing in the risks, because a gap left out of the
  risks is a gap the candidate walks into unprepared

These are cheap assertions, not a guarantee of correctness. They catch
structural breakage and broken reference chains. They cannot catch output that
is structurally valid and semantically wrong — only the evaluation set does
that.

## The governed evidence loop

The loop around the workflow consults a model at exactly two points — parsing
an optional round description, and assessing whether an answer evidences a
requirement — and both outputs face code-owned gates. Everything else,
including what happens next, is computed.

**The queue.** Gaps are processed exactly once each, in a deterministic
order: verdicts at GAP coverage whose requirement is known and not yet
processed, sorted by importance descending (missing importance sorts last)
then requirement identifier ascending. Processed means asked once, not
resolved — a rejected answer does not requeue its requirement. Routing is a
pure function: an invalid initial package stops the run; a current gap with
question budget remaining goes to the interrupt; an exhausted ceiling with
gaps remaining proceeds to final generation, noted in the trace; an empty
queue proceeds to final generation.

**The question** is built by code from the requirement's own text — one
specific example, the method, the result — so what the human is asked never
depends on a model.

**Admission gates**, applied in order of cheapness and trust to each resumed
answer after one short-context model assessment (target requirement, question
and answer only — the assessor never sees the wider run):

1. the stripped answer meets the length floor
   (``min_clarification_length``, default 24) — checked before any model
   judgment is consulted
2. the assessment's target equals the requirement actually asked — model
   output cannot redirect evidence
3. the assessment's verdict is valid
4. the accepted claim is non-empty after stripping

**Accepted claim as evidence.** An admitted answer mints a ``CL-`` evidence
item whose summary is the accepted claim — the faithful restatement that
survived the rubric and the gates — never the raw answer, so wording that was
not admitted cannot influence matching. Provenance carries the requirement
addressed and the question asked.

**The audit record.** Every processed gap appends one record, admitted or
not: requirement identifier, question, raw answer, the full assessment
(target, verdict, relevance and specificity reasons, claim), the accepted
flag, the decision reason, and the accepted claim when admitted. The records
land in ``clarification_records.json`` beside the stage artifacts; the raw
answer lives here, in the audit trail, not in evidence.

**Round context.** Optional freeform text about the upcoming round is parsed
once, before the initial generation, into a structured context (type, format,
interviewer roles, focus, notes — all optional; absent text means none and
general-purpose preparation). It threads into the strategy and question
prompts only. The invariant: round context changes what to emphasize, never
what the candidate can claim — extraction and matching never see it, and the
matches are identical with and without one.

**Two generations.** The workflow runs once before the queue opens and once
after it closes, over the original corpus plus every admitted claim plus the
round context. No regeneration happens between answers.

## Evaluation

Two kinds exist in principle; one exists in practice.

**Behavioral regression — shipped.** A dataset of scenarios freezes reference
behavior for the agent graph. Each scenario declares its suites, its inputs
per run — a fixture profile over the repo's own sample posting, optional
round text, scripted answers and assessments — and its reference outputs: a
trajectory template, the interrupt count, the processed, accepted, rejected
and remaining-gap identifier sets, package validity and the stop reason.
Trajectory templates were authored by running this repo's graph and
recording, so they are facts about this code, not aspirations.

The target drives the real compiled graph through interrupt and resume;
evaluators score three layers:

1. **Trajectory** — strict match of every turn's node sequence against the
   frozen template.
2. **State** — gap processing (identifiers and interrupt counts) and
   admission sets (accepted, rejected, remaining, audit completeness, and
   the invariant that no identifier is both accepted and rejected).
3. **Outcome** — package validity and stop reason, plus a null-safe check
   that round context changed guidance while evidence and coverage held
   still.

Suite semantics: the **offline** suite injects a deterministic fixture
provider through the same seam production uses and runs in continuous
integration — a red cell fails the build. The **live** suite wraps the real
provider in a counting one so a model-backed evaluator can assert genuine
calls happened; it needs credentials and never runs in CI.

What this proves: a change that alters the loop's behavior — its path, its
questions, its admissions, its terminations — cannot merge silently. The
recorded fire drill in [`FAILURE-ANALYSIS.md`](FAILURE-ANALYSIS.md) shows the
suite catching a deliberately introduced regression that every outcome-level
check accepted. What this deliberately does not prove: that any verdict,
strategy or question is *good*. A frozen behavior can be a frozen mistake.

**Quality evaluation — open.** Scoring the system against hand-labelled
reference data does not exist yet. The needed set is unchanged: real postings
with labelled verdicts, scored on false-gap and false-proof rates separately,
since the two costs are not symmetric — a false gap wastes preparation time,
while a false proof leaves a real weakness unprepared. Until it exists, no
claim that one path is better than another is measurable here.

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
