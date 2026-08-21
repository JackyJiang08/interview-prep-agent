# Failure analysis: a deliberate regression

A suite nobody has seen catch a bug is an untested alarm. This document
records one controlled experiment: a plausible product change introduced on a
throwaway branch, the regression matrix that caught it, and what the shape of
the catch says about outcome-only checking. Every matrix below is pasted from
the real runs; the branch was deleted without merging.

## The change

One inserted guard in the queue selection, five lines:

```python
# Product change: one clarification per run is enough; stop selecting
# after the first processed requirement to keep runs short.
if processed:
    return None
```

The motivation is entirely plausible. Interrupting a human three times per run
is real friction; a product owner asking "can we cap it at one question?" is
asking for exactly this. Nothing about the change looks like a bug: it is
small, readable, intentional, and every gate in the system still passes it.

## Baseline — main, before the change

```
=== BASELINE: pytest on main ===
139 passed in 0.46s
=== BASELINE: offline suite on main ===
scenario                     graph_trajectory_strict_match  all_gaps_processed  admission_set_correct  terminal_state_valid  round_guidance_changed
complete-profile-no-round    PASS                           PASS                PASS                   PASS                  PASS
round-guidance-comparison    PASS                           PASS                PASS                   PASS                  PASS
mixed-clarifications         PASS                           PASS                PASS                   PASS                  PASS
all-clarifications-rejected  PASS                           PASS                PASS                   PASS                  PASS
wrong-target-assessment      PASS                           PASS                PASS                   PASS                  PASS
exit 0
```

## With the change — the throwaway branch

```
=== EXPERIMENT: offline suite with the cap ===
scenario                     graph_trajectory_strict_match  all_gaps_processed  admission_set_correct  terminal_state_valid  round_guidance_changed
complete-profile-no-round    PASS                           PASS                PASS                   PASS                  PASS
round-guidance-comparison    PASS                           PASS                PASS                   PASS                  PASS
mixed-clarifications         FAIL                           FAIL                FAIL                   PASS                  PASS
all-clarifications-rejected  FAIL                           FAIL                FAIL                   PASS                  PASS
wrong-target-assessment      FAIL                           FAIL                FAIL                   PASS                  PASS
exit 1
```

Per scenario:

* **complete-profile-no-round** and **round-guidance-comparison** stayed fully
  green. Their corpus has no gaps, so the capped code path never runs — the
  right result, and itself informative: the suite localizes the change to
  gap-processing scenarios rather than flagging everything.
* **mixed-clarifications**, **all-clarifications-rejected** and
  **wrong-target-assessment** turned red on all three behavioral evaluators —
  trajectory, gap processing, and admission sets — while **terminal state
  stayed green on every one of them**. The build fails on the behavioral
  layers alone.

## The first divergent step

Reference trajectory for the gapped scenarios, second turn:

```
["assess_and_admit", "observe", "ask", "__interrupt__"]
```

Observed with the cap:

```
["assess_and_admit", "observe", "generate_final"]
```

The divergence is the third step of turn two: after the first answer is
assessed, `observe` selects nothing — the cap returns `None` with two
unprocessed gaps still in the queue — and the run routes to `generate_final`
instead of `ask`. Concretely, on the mixed scenario:

```
interrupts: 1  (expected 3)      processed: [REQ-002]  (expected all three)
accepted:  [REQ-002]             rejected:  []          (expected [REQ-005])
remaining gaps: [REQ-005, REQ-006]
package_valid: True              stop: valid_package_complete
```

## Why a structurally valid package concealed it

The final package is *correct by construction* even under the cap. The two
unasked requirements are still gaps; gaps still surface as risks; every
citation still resolves; the question floor is still met; the package gate
passes, honestly, because nothing structural is wrong. The stop reason is
`valid_package_complete` — the same terminal state as a full run.

That is the concealment: the system quietly stopped doing two-thirds of its
human-in-the-loop work, and every outcome-level signal — package validity,
stop reason, gate errors, exit codes of a normal run — reported success. The
loss is invisible in the artifact and visible only in the behavior: one
interrupt instead of three, a processed set of one, an audit trail with two
records missing.

## What this implies about outcome-only checks

An outcome check answers "is what came out well-formed?" It cannot answer
"did the system do what it is for?" — because a system that silently does
less usually produces output that is *more* likely to be well-formed, not
less. Any change that trades away work tends to pass outcome checks by
default. Behavior has to be part of the contract: the trajectory, the state
deltas, the counts of the interactions that are the product's reason to
exist.

## Restored — main, after deleting the branch

```
=== RESTORED: offline suite on main ===
scenario                     graph_trajectory_strict_match  all_gaps_processed  admission_set_correct  terminal_state_valid  round_guidance_changed
complete-profile-no-round    PASS                           PASS                PASS                   PASS                  PASS
round-guidance-comparison    PASS                           PASS                PASS                   PASS                  PASS
mixed-clarifications         PASS                           PASS                PASS                   PASS                  PASS
all-clarifications-rejected  PASS                           PASS                PASS                   PASS                  PASS
wrong-target-assessment      PASS                           PASS                PASS                   PASS                  PASS
exit 0
```

One sentence, which is the whole point: **outcome validity is necessary, not
sufficient.**
