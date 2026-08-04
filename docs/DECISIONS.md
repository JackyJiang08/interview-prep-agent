# Decisions

A record of choices that are not obvious from reading the code, with the
reasoning that produced them. Where a decision has a known cost, the cost is
stated rather than left for a reader to discover.

## Fixed control flow in the workflow layer

Extraction, matching and assembly run in the same order on every invocation,
with no runtime branch. The reason is narrow: none of the three steps produces
a result that could change which step comes next, so a decision mechanism would
add cost — reduced reproducibility, a larger surface to test — while buying
nothing. This is a claim about these three steps only, not an argument against
agency in general; genuine decisions appear as soon as the system can call tools
or receive feedback, and that is where a bounded loop belongs.

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

## Supporting Python 3.9 while testing 3.11 and 3.12

The package declares `requires-python = ">=3.9"` and the lint configuration
disables the PEP 604 rewrites (`Optional[str]` to `str | None`), because Pydantic
evaluates annotations at run time and that syntax raises `TypeError` on 3.9.
Continuous integration covers 3.11 and 3.12 only. This is a known inconsistency:
3.9 support is real enough to constrain the code but is not verified on every
commit. The choice is to keep the floor until there is a reason to raise it,
then drop the ignore list and the constraint together.
