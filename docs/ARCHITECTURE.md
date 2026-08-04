# Architecture

Why this is built in layers, what each layer owns, how they meet, and what has
to be true before the next one is worth building.

## The organising principle

Autonomy is a cost, not a feature. A component that decides its own next step is
harder to test, harder to reproduce, and harder to debug than one that does not,
because a failure can now come from the decision as well as from the work. That
cost is worth paying exactly when there is a real decision to make — a point
where the right next step depends on information not available until run time.

So the question asked of every capability here is narrow: *at this point, does
the correct next step depend on something only discoverable at run time?* If no,
the step belongs in fixed control flow. If yes, it belongs in a bounded decision
loop, and the loop is scoped to that point rather than wrapped around everything.

Applied to this system, the answer is no three times over for extraction,
matching and assembly — and yes as soon as the system can call a tool, discover
that evidence is missing, or receive feedback contradicting what it produced.
That split is the architecture.

A second constraint runs through all of it. Whatever a layer produces has to
stay attributable: every claim points at the thing that justifies it, and no
layer may weaken a guarantee established below it. A layer that can silently
overwrite grounded text is a layer that has removed the reason to trust the
output at all.

## Layer 1 — deterministic workflow · shipped

**Owns** extraction of requirements from a posting, scoring them against an
evidence corpus, and assembling a gap-first plan. Enforces the coverage,
traceability and grounding gates.

**Why fixed.** Extraction always precedes matching, matching always precedes
assembly, and no result of one step can change which step comes next. There is
no branch, so nothing is gained by allowing one — and the cost of allowing it is
that a plan could no longer be reproduced from the same inputs.

**Boundary.** Everything crosses it as a validated model in `models.py`:
`Requirement`, `EvidenceItem`, `RequirementMatch`, `FocusPlan`. These are the
contract the whole system shares, which is why they sit at package root rather
than inside `workflow/`. Higher layers depend on the contract, not on the
implementation behind it.

**Open inside this layer.** Lexical matching is the dominant error source; a
semantic scorer belongs behind the existing matcher seam. Bundled requirement
lines need splitting. The match threshold needs calibrating against real data
rather than one synthetic example.

## Layer 2 — bounded decision layer · next

**Owns** the choice of what to do when the fixed path runs out. Three points in
this system produce genuine decisions:

1. **Missing evidence.** The corpus is thin on a requirement. Asking the
   candidate is cheap and high value, but asking about everything is worthless —
   which gap to raise depends on what the plan currently looks like.
2. **Tool results.** A research call can return something useful, something
   irrelevant, or nothing at all. What to do next depends on which happened, and
   that is not knowable in advance. Handling failure honestly matters more than
   handling success: a tool that returns nothing must produce a recorded absence,
   never a plausible invention.
3. **Feedback after the fact.** An interview reveals which answers were weak.
   Which part of the plan that invalidates depends on the content of the
   feedback.

**Shape.** A small closed set of actions, each with a declared effect on state;
a step limit that terminates the loop regardless; a recorded reason for every
action taken. Closed rather than open-ended because an action set that can grow
at run time cannot be tested, and the point of bounding it is that the set of
things that can go wrong stays enumerable.

**Boundary.** Reads a `FocusPlan` and the evidence corpus; may re-run Layer 1
stages; emits an updated plan plus a trajectory record. The hard constraint: it
may add evidence and revise commentary, but it may not rewrite the verbatim
requirement text carried up from extraction. Grounding is established at the
bottom and every layer above inherits it unchanged.

**Ships when:**

* at least one real tool exists, with its failure mode defined and tested — a
  loop with nothing to call is a loop with no decision to make
* execution traces exist, because a wrong trajectory cannot be debugged from a
  final answer alone, and adding traces after the fact means debugging blind in
  the interim
* an evaluation set exists showing the loop does not degrade what Layer 1
  already produces correctly

## Layer 3 — durable state · planned

**Owns** continuity. Research results and interview feedback arrive after a plan
exists, and should update it rather than trigger a regeneration.

**Why not regenerate.** Regeneration throws away work the candidate has already
read and reasoned about, and makes two successive plans incomparable — there is
no way to see what changed or why. Incremental update keeps a history, and a
history is what makes the system's behaviour auditable over time.

**Boundary.** A serialisable record holding the current plan, its provenance,
and what has been learned so far. Layer 2 reads it at the start of a turn and
writes it at the end; Layer 1 stays stateless and unaware of it.

**Ships when:**

* the state has a versioned schema, so an old record is either readable or
  explicitly rejected, never silently misread
* updates are idempotent — applying the same new fact twice leaves the same
  state, which is what makes retries safe
* there is a defined rule for what a newly learned fact may overwrite. Without
  one, the most recent write wins by accident rather than by design, and
  correcting a mistake becomes indistinguishable from introducing one

## Cross-cutting — traces, evaluation, failure analysis · planned

**Traces.** One record per run: the inputs, each step, each decision and its
reason, each artifact. Layer 1 approximates this today by writing a JSON file
per stage — `examples/trace/` holds one such run over the committed inputs.
That stops being sufficient the moment control flow varies between runs, because
the interesting question changes from "what did each stage output?" to "why did
this run take a different path?"

**Evaluation.** A set of real postings with hand-labelled verdicts, scoring
false gaps and false proofs separately: a false gap wastes preparation time,
while a false proof leaves a real weakness unaddressed. These costs are not
symmetric and a single accuracy number hides the difference.

This gates most of the work above. Without it, semantic matching, a decision
loop, and threshold changes are all unfalsifiable — each can be shipped, none
can be shown to help.

**Failure analysis.** Written up, kept in the repo, and specific: what was
expected, what happened, which layer produced it, what changed as a result. A
list of fixed bugs is not the same artifact; the value is in the pattern across
failures, which is what tells you whether the next layer is worth building or
the current one is not finished.

## What this architecture gives up

Stating the cost plainly, since the layering is a choice and not a free one:

* **Latency and cost, later.** A bounded loop with tool calls will be slower and
  more expensive than one prompt. It buys attributability, and that trade is
  only worth it because an unverifiable plan is worth little here.
* **Speed of building now.** Fixed stages with validated boundaries take longer
  to write than a single call, and Layer 1 solves a narrower problem than the
  full system in exchange.
* **Flexibility at the edges.** A closed action set cannot handle a case nobody
  anticipated. The system will refuse or stop where an open-ended one would
  improvise — which is the intended behaviour, but it is still a limitation.
