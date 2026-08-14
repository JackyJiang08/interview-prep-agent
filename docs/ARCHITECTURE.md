# Architecture

Why this is built in layers, what each layer owns, how they meet, and what has
to be true before the next one is worth building.

## The problem being solved

Preparing for a specific interview is a research task with a deadline. A posting
states a dozen requirements, the candidate has a body of real experience, and
somewhere in the gap between the two sits the small set of things actually worth
rehearsing. Finding that set takes more than one comparison: it means looking up
what the company ships, noticing which claims are thin, and revising after the
first conversation reveals what a panel really probes.

Handing all of that to a single model prompt fails in the way
[`METHODOLOGY.md`](METHODOLOGY.md) describes: fluent output whose claims can be
checked against nothing. This project answers along two axes — every claim
carries a pointer to its source, and capability is added a layer at a time,
each layer no more autonomous than its own decisions require. The rest of this
document is the second axis worked out in full.

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

**Owns** the full fixed path from source documents to a validated preparation
package: input validation, evidence normalization, requirement extraction,
coverage matching, deterministic gap assessment, strategy and question
composition, and a package gate whose outcome routes the run into assembly or
an error report. Enforces every deterministic guarantee — grounding, match
consistency, and the end-to-end identifier chain.

Four stages are model-backed — extraction, matching, strategy, questions —
and all four sit behind one provider seam, so no stage touches a vendor SDK.
Each model produces data against a requested schema; every judgment about that
data belongs to gate code. The extraction paths share one grounding gate, the
matcher paths share one match gate, and the composed layers are judged once,
by the package gate. The models are used to read and to write; the gates
decide what was really there.

**Why still fixed.** Every stage runs in the same order on every invocation,
and both forks — invalid extraction on the short graph, a failed package gate
on the full one — are taken by pure predicates over booleans that gate code
computed, with all targets wired when the graphs are built. Nothing chooses at
run time. The model-backed stages are the nondeterministic elements, and what
they produce is data that must survive validation, never a routing choice; no
model approves its own output.

**Boundary.** Everything crosses it as a validated model in `models.py`:
`Requirement`, `EvidenceItem`, `RequirementMatch`, `FocusArea`,
`InterviewStrategy`, `MockQuestion`, `PrepPackage`. These are the contract the
whole system shares, which is why they sit at package root rather than inside
`workflow/`. Higher layers depend on the contract, not on the implementation
behind it.

**Open inside this layer.** The lexical matcher's false gaps remain its
dominant error, and the model matcher that exists to close them is itself
unmeasured — as are model extraction, the strategy, and the questions. The
match threshold needs calibrating against real data rather than one synthetic
example. All of it waits on the evaluation set.

## Layer 2 — bounded decision layer · shipped, unevaluated

**Owns** the choice of what to do when the fixed path runs out. The decision
this repo's data actually produces is the first of the three anticipated —
missing evidence: the corpus is thin on a high-importance requirement, asking
the candidate is cheap and high value, but asking about everything is
worthless, so *which* gap to raise depends on what the run currently looks
like. That decision is now real and the loop is built around it.

**Mechanics, as built.** The loop is observe → decide → authorize, with every
branch target fixed at build time:

* **Observation compression.** Pure code derives a factual snapshot — package
  state, high-priority gaps (GAP coverage, importance ≥ 4, sorted), what has
  been asked, budget remaining — and the *allowed* action set. The model sees
  this snapshot and nothing else.
* **Proposal.** One structured-output call returns exactly one action from
  `ASK_USER | GENERATE_PREP_PACKAGE | FINISH` with a one-sentence reason.
  Only the validated decision enters state; that proposal is the model's
  entire authority.
* **Authorization.** Code applies every gate — action budget, allowed set,
  ask eligibility and non-repetition, the question ceiling, finish
  preconditions — and computes the route the conditional edge maps. An
  invalid proposal is retried once with the rejection fed back, then the run
  stops with `invalid_decision`; an exhausted budget stops without retry
  (`action_budget_exhausted`), because a retry cannot refill it; a completed
  run stops with `valid_package_complete`.
* **The human capability.** `ASK_USER` interrupts with the requirement and
  one focused factual question. The answer is minted as a first-class `CL-`
  evidence item and regeneration passes the enlarged corpus through the
  unchanged workflow, so the traceability guarantee survives the human in
  the loop. Budgets — actions and questions — are settings enforced by
  authorization, not suggestions in a prompt.

**Boundary.** The hard constraint holds: the loop may add evidence and
regenerate, but it may not rewrite the verbatim requirement text carried up
from extraction. Grounding is established at the bottom and every layer above
inherits it unchanged.

**Ship criteria: two of three met.** The bar this document set was a real
tool with a defined failure mode, traces good enough to debug a wrong
trajectory, and an evaluation set showing the loop does not degrade Layer 1.
The interrupt capability is that tool — its failure modes (no answer path,
repeated targets, budget exhaustion) are defined and tested — and
`agent_trace.json` records every observation, proposal, authorization verdict
and stop reason in order. The evaluation set does not exist. That criterion
is not weakened by the other two being met: until packages produced with the
loop are measured against plain workflow runs, this layer is a capability,
not a proven improvement, and it is not called done here.

**What Layer 3 still owes.** State across runs — a thread survives its own
interrupts, but nothing survives the process — and feedback rounds beyond a
single question: the tool-results and post-interview decisions anticipated
above remain unbuilt, and both belong to durable state.

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
