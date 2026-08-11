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
