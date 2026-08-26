# Decisions

A record of choices that are not obvious from reading the code, with the
reasoning that produced them. Where a decision has a known cost, the cost is
stated rather than left for a reader to discover.

## Fixed control flow in the workflow layer

Extraction, matching and assembly run in the same order on every invocation.
The reason is narrow: none of these steps produces a result that could change
which step comes next, so a decision mechanism would add cost — reduced
reproducibility, a larger surface to test — while buying nothing. This is a
claim about these steps only, not an argument against agency in general;
genuine decisions appear as soon as the system can call tools or receive
feedback, and that is where a bounded loop belongs.

The graph does contain one branch, to the error report when requirement
validation fails. That is not a counterexample: both targets are fixed when the
graph is built, and the predicate is a pure function of a boolean that gate code
computed. Nothing chooses at run time; the branch only spares the caller from
matching against requirements already known to be broken.

## A graph runtime for a fixed workflow

The stages moved onto a state graph without gaining any autonomy. The gain is
that the shape is now declared in one place instead of implied by the order of
calls in a function, and that each node's inputs and outputs are visible at the
boundary rather than buried in a call stack. That matters ahead of a decision
layer: adding one later means adding nodes and edges to a structure that already
exists, rather than restructuring a straight-line function under time pressure.

The cost is a dependency on a runtime for something a sequence of calls did
adequately, and a layer of indirection between the command line and the work.
Worth it only because of what is planned next; on its own it would be premature.

## Model-backed extraction behind a provider seam

Extraction has two implementations: the original lexical splitter and a
model-backed path. Neither is a fallback for the other. The lexical path is the
default because it is deterministic, offline, and free, which is what the
committed example, the tests and continuous integration all need. The
model-backed path exists because line splitting cannot read a posting written as
prose, and cannot separate a sentence that bundles three demands into one line.

The model call sits behind an abstract seam, and no stage imports a vendor SDK.
This is the difference between a provider-agnostic design and a claim of one.
Its response is never trusted: it is validated against the same Pydantic model
the lexical path produces, checked for the fields only that path can supply, and
then put through the same grounding gate. A model that returns a plausible
requirement with a quote that is not in the posting fails exactly as loudly as a
bug in the splitter would.

## One requirement model, not two

The model-backed path adds a category, an importance score, a must-have flag and
a source quote. These extend the existing `Requirement` rather than forming a
parallel model, because two models would mean two definitions of what a
requirement is, drifting apart at every change, and a conversion between them
that could silently lose the grounding field.

The cost is that fields the lexical path cannot supply are optional, so the type
alone no longer tells you a category is present. That is honest — the lexical
path genuinely does not know the category — and it is the gate, not the type,
that enforces completeness where completeness is required.

## No fixture fallback on model failure

When a model call fails — network, quota, or a response that fails validation —
the run fails. It does not fall back to canned data, retry with a weaker
schema, or degrade to the lexical path silently. The temptation is real: a
fallback keeps demos smooth. But the gates exist to give one guarantee, that
whatever comes out of a run was actually computed from the supplied inputs and
checked against them. Output silently substituted from a fixture satisfies
every structural check while being about nobody, which is worse than an error
because it cannot be distinguished from a real result afterwards. A user who
wants the offline behaviour chooses it explicitly with the lexical flags.

## The model only ever proposes

In the first decision loop, the model's entire authority was one proposed
action per cycle, chosen from a set that code derived before the model was
consulted. Code authorized, routed, executed, counted the budget down, and
stopped the run. The alternative — letting the model route directly, or
letting it decide when it was finished — would have been less code and fewer
round trips. It was rejected because authority that lives in one place can be
audited in one place: every gate is a pure function with a hand-built failing
test, and a wrong trajectory is debuggable by reading which proposal was
rejected and why. The cost was a loop that is more machinery than prompt, and
a model that can be overruled by its own runtime — which was the point. The
next entry records where this design went from there.

## The proposal step retired in the second agent iteration

The proposal step is gone. Once the rule became "process every gap exactly
once in a deterministic order," the next action stopped being a decision and
became a computable function of the queue and the budgets — and this repo's
organising principle, autonomy proportional to the decision, applies in both
directions. A model proposal over what is effectively a one-element action
set is autonomy theater: it costs a round trip, a retry path and an
authorization surface to arrive at the answer code already knew. Routing
returned to pure code.

The model's judgment did not shrink to nothing; it moved to the two questions
code genuinely cannot answer — what kind of interview round a freeform
description denotes, and whether a human's answer actually evidences a
requirement — and both stay behind code-owned gates that its output cannot
bypass or redirect. The trade, stated plainly: the loop is less "agentic" by
vocabulary and more trustworthy by construction. A system that consults a
model only where a model is needed has fewer places to be wrong, and every
one of them is gated.

## Evidence carries the accepted claim, not the raw answer

An admitted clarification mints evidence whose summary is the claim the
assessment extracted and the gates approved — never the raw answer. The raw
answer is not lost: the audit record keeps it, beside the full assessment,
the verdict and the decision reason. The split is deliberate. An answer is
whatever a human typed under pressure — hedges, tangents, overstatement; the
accepted claim is the part that survived a faithfulness rubric and four
deterministic gates. Matching against the raw answer would let wording that
was never admitted influence coverage. The cost is that evidence text is one
step removed from what the human literally said, which is exactly why the
audit record preserves the original next to what was made of it.

## One regeneration after the queue closes

Answers accumulate; the workflow runs again exactly once, after the last gap
is processed. The per-answer alternative — regenerate after every admission —
was rejected: it multiplies cost by the queue length, produces intermediate
packages nobody reads, and lets early answers shape the context in which
later gaps are asked about, making the run order-sensitive for no gain. One
final run gives every admitted claim the same canonical context and bounds
the whole loop at two workflow invocations. The cost is that the human
answers all questions against the initial package's picture of the gaps,
which is acceptable precisely because questions are generated from
requirements, not from intermediate matching.

## Clarifications become evidence, not prompt context

A human answer at an interrupt could simply be appended to the next prompt.
It is instead minted as a first-class evidence item in its own CL- series,
with the requirement it addresses and the question asked as provenance, and
the package is regenerated over the enlarged corpus through the unchanged
workflow. The reason is the system's one guarantee: every claim cites a
resolvable source. An answer that lives only in a prompt is exactly the kind
of unattributable input the gates exist to keep out — a match influenced by
it would cite nothing. As evidence, the answer is matched, scored, cited and
gate-checked like anything else, so traceability survives the human in the
loop. The cost is a full regeneration per answer instead of an incremental
patch; incremental update is Layer 3's problem, deliberately.

## Budgets are settings, not constants

The action budget, the question ceiling and the clarification length floor
live in ``Settings`` beside the matching bounds, not as constants in the agent
module. They are operational limits a deployment should be able to tighten or
relax without editing code — a cautious run wants one question; a batch
evaluation wants zero — and putting them beside the other tunables keeps
every bound the system enforces discoverable in one file. The routing and
admission code read them at graph build time; nothing in a prompt can change
them. The defaults follow the queue: every gap once, an action budget derived
from the queue size under a hard cap. The ceilings are load-bearing either
way: they are what makes "bounded" a property of the code rather than a
description of intent.

## Regression before quality

The first evaluation shipped is a behavioral regression suite, not a quality
benchmark. That is sequencing, not preference. Behavior contracts are cheap
to author (record what the code does today), deterministic to check (fixture
providers through the seam), and enforceable in continuous integration from
day one. Quality measurement needs labelled reference data that does not
exist yet, and pretending a regression suite is a quality benchmark would be
the exact overclaim this repo's limitations section exists to prevent. The
cost of the ordering is stated everywhere the suite is described: a frozen
behavior can be a frozen mistake, and green cells prove stability, not merit.

## Provider injection over client patching

The suites drive the real compiled graph with providers injected through the
same ``model=`` seam production uses — a fixture provider offline, a counting
wrapper around the real one live. The alternative, monkeypatching client
constructors and module attributes, was rejected because it bypasses the one
boundary this repo promises to keep: no stage touches a vendor SDK, and
everything model-shaped enters through the seam. Patching would test a
runtime the production code never has, and every patch site is a place the
test can drift from reality. The seam was the test hook all along; the
evaluation suite using it is evidence the boundary is real. A side effect
worth naming: extraction and matching stay live code under the offline
suite, so the fixtures cover less and the production paths cover more.

## The deliberate-regression record

A suite nobody has seen catch a bug is an untested alarm. Before the
regression suite was documented as protection, it was made to fire once, on
purpose: a plausible one-question cap introduced on a throwaway branch, the
red matrix captured, the branch deleted, the restored green captured —
[`FAILURE-ANALYSIS.md`](FAILURE-ANALYSIS.md) is the record. The experiment
also produced the suite's sharpest justification: the capped run's package
was structurally valid and its stop reason terminal-normal, so every
outcome-level signal reported success while two-thirds of the loop's work
silently disappeared. The cost was an afternoon; the alternative was
shipping an alarm that had never rung.

## What the second provider cost

The provider seam has promised since it was written that "adding a second
provider means adding a file here and nothing else." Adding Azure OpenAI
tested that claim, and it mostly held: ``providers/azure.py`` is a new file
implementing the same two-method contract, registered by three lines in the
package's ``build_model``. No stage, gate, graph or prompt changed. The
evaluation suite, the workflow and the agent were untouched.

Three things did leak, and they are worth naming rather than glossing:

1. **Selection had to reach the surfaces.** A seam with one implementation
   needs no chooser; a seam with two does. ``--provider`` was added to the
   prep, agent and eval commands, and to session creation. That is inherent
   to having a choice, not a flaw in the seam.
2. **Credential shape is provider-specific.** Gemini needs one key; Azure
   needs an endpoint, a key and a deployment name. The server's refusal path
   had to learn which settings each provider requires, because a useful error
   message names the missing one.
3. **One schema adaptation.** Azure's strict structured-output mode requires
   every object to forbid extra properties and to list every property as
   required — including optional ones. Pydantic emits the first and not the
   second, so the provider walks the schema and closes the gap. This is
   genuinely provider-shaped work, and it is confined to the provider file,
   which is where the seam intends such work to live.

The honest summary: the seam contained the vendor SDK and the request shape
completely, and did not contain — could not contain — the fact that two
options require a way to pick between them. That is the right division. The
cost of the second provider was one file, one registry entry, one flag on
three commands, and a handful of fields on one request model.

## Tracing lives inside the seam, off by default

Optional observability is wired at exactly one place: the provider
implementation, behind two environment variables that must both be set before
anything is wrapped. Off means no wrapper, no upload, and no network beyond
the model call itself; no stage, node or gate knows tracing exists. The
alternative — instrumenting nodes directly — would spread an operational
concern through business logic and make "zero overhead when off" a claim about
many files instead of one. The cost is coarser traces than per-node
instrumentation could give; that is the observability layer's job, later, done
deliberately. Traced runs upload prompts and responses to the tracing service,
which is why the example environment file says to use synthetic data.

## YAML stays the canonical evidence input

A markdown resume is accepted and its bullets normalize into the same evidence
model, but the YAML corpus remains the canonical form. A corpus entry is
written *as evidence* — one attested claim, its skills, its impact — while a
resume bullet is written to impress and must be reinterpreted, so the corpus
is the higher-fidelity input and the resume reader is a convenience ramp, not
a replacement. Identifiers are minted once, at the boundary, in either route;
nothing downstream mints one. The cost of the ramp is that a badly formatted
resume yields fragmented evidence — visible in the artifacts rather than
hidden, which is the most that can be claimed for it.

## Coverage as three levels, mapped honestly per matcher

Verdicts carry FULL, PARTIAL or GAP, with the old binary PROOF/GAP kept as the
degenerate view (anything but a gap is proof). The lexical matcher never emits
PARTIAL: term overlap can measure how much vocabulary the evidence attests but
cannot recognise that the unattested part is an important *dimension* — that
takes reading, so claiming PARTIAL from a middling score would dress ignorance
up as judgment. Only the model path, which reads, may say PARTIAL, and both
paths pass the same deterministic guard: a gap cites nothing, anything else
cites at least one real evidence item, every requirement is judged exactly
once, in order.

## Focus priority as importance times coverage weight

Preparation order is computed, not judged: requirement importance (1–5)
multiplied by a coverage weight (FULL 1, PARTIAL 2, GAP 3), descending, ties in
source order. A gap on a critical requirement lands first; a covered
nice-to-have lands last. When importance is absent — the lexical extractor
cannot supply one — the neutral weight 1 is used, and the ordering degrades to
exactly the old gap-first rule, which is what keeps the committed artifacts
byte-stable under the upgrade. The weights are a modelling choice, not a
measurement; they are three small integers precisely so that nobody mistakes
them for one.

## Lexical scoring before semantic scoring

The matcher weights terms by inverse document frequency and scores the share of
a requirement's weighted terms that an evidence item attests. An embedding-based
scorer would almost certainly be more accurate. It was still the wrong thing to
build first, because there is no evaluation set yet: a semantic matcher's output
cannot be checked by reading it, so shipping one now would mean trading a method
whose errors are visible for a method whose errors are merely plausible. The
cost is real and is the system's dominant error source — "designed randomized
experiments" scores zero against "A/B testing" — and closing it is the first
thing to do once there is labelled data to measure the change against.

## Gates that raise rather than degrade

Coverage and traceability violations raise `QualityGateError` and abort the run
instead of returning a partial plan with a warning. A plan that quietly dropped
a requirement, or cited evidence that does not exist, is worse than no plan: it
looks complete, so nobody checks it, and the whole premise here is that output
should be checkable. Failing loudly costs the occasional aborted run in
exchange for never silently shipping a plan that violates a stated guarantee.

## The 0.30 match threshold

The default threshold was set by running the pipeline on one synthetic example
and picking a value that separated the cases sensibly. It is a guess, labelled
as a guess in the README, and it is the single most arbitrary number in the
system. It stays for now because tuning it against one example would produce a
figure that merely looked principled; the honest fix is calibration against a
labelled set, scoring false gaps and false proofs separately, since the two
costs are not symmetric.

## Committed output under `examples/trace/`

Generated artifacts are normally kept out of version control. These are checked
in because the inputs are synthetic and committed, which makes the output a
deterministic function of the repo: it changes only when behaviour changes. That
turns an unexpected diff into a signal, and lets a reader see the stage
boundaries without installing anything.

## Raising the Python floor to 3.11

The package previously declared `requires-python = ">=3.9"` while testing only
3.11 and 3.12 — support real enough to constrain the code but never verified.
That was recorded here as a known inconsistency, to be resolved when something
forced it. The workflow runtime forced it: both it and the provider SDK require
3.10 or newer.

The floor is now 3.11 rather than 3.10, so that the declared range is exactly
the range continuous integration actually runs. Claiming 3.10 without a job covering
it would recreate the inconsistency this entry was written about. Two things
went with it: the lint exemption for PEP 604 unions, which existed only for 3.9,
and the hand-rolled `str, Enum` pairs, now `StrEnum`.

## Requirement count bounds set wide

The requirement gate rejects a set that is too small or too large, with defaults
of 1 and 50. Those bounds are deliberately loose. They exist to catch degenerate
extraction — nothing at all, or a runaway list — not to encode an opinion about
how long a posting should be, and a tighter default would reject short but
perfectly real postings. The extraction prompt asks for a much narrower range,
and the bounds are configurable for callers who want to hold a model to it.

The cost is that a moderately wrong count passes. Catching that needs an
evaluation set, not a tighter constant.

## The image stays public

The container image the deploy workflow pushes to the registry starts
private, and the deployment leaves it public instead. The reasoning is that
nothing argues for privacy: it is a public demo of a public repository, and
the image is a deterministic function of that repository — no key, no
credential, no private input bakes into it, which the keyless-by-design
session layer already guarantees. What publicity buys is one fewer
credential surface: a private image needs a registry credential registered
on the Container App and a token that someone must scope, store and
eventually rotate. The cost is that anyone can pull and inspect the image —
which here discloses exactly what the repository already discloses.

## Scale to zero, with the wake absorbed in the page

The Container App runs zero replicas when idle. For a credit-funded demo
that is the difference between costing approximately nothing and paying for
an always-on replica nobody is using; it is also the setting that caps a
runaway bill, together with the one-replica ceiling.

The cost lands on the first visitor after an idle stretch: their request
waits out a container start measured in seconds, and a landing page that
failed or hung there would read as a dead project. The trade is accepted
and the cost absorbed in the interface — the demo fetch runs under a short
timeout, a miss shows one line naming what is happening, and retries back
off until the server answers. The alternative, a minimum of one replica,
buys latency for the first visitor with an idle bill for everyone else, and
a demonstration does not have the traffic to justify it.
