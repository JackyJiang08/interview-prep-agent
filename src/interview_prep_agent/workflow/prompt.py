"""The extraction prompt.

Written as constraints rather than encouragement. Every rule here has a
matching deterministic check in :mod:`.gates`, because a rule the code cannot
verify is a hope rather than a constraint — the prompt asks, the gate decides.
"""

from __future__ import annotations

MIN_REQUESTED = 6
MAX_REQUESTED = 10

INSTRUCTIONS = f"""\
You read one job posting and return the requirements it states.

Return between {MIN_REQUESTED} and {MAX_REQUESTED} requirements. Split a
sentence that bundles several distinct demands into one requirement each, and
merge restatements of the same demand into one.

For every requirement:

- id: sequential from REQ-001, in the order the requirements appear in the
  posting, formatted with three digits.
- text: the demand stated plainly in one sentence.
- normalized: text lowercased, with surrounding punctuation removed. Used for
  comparison only.
- source_quote: a span copied character for character from the posting that
  states this requirement. Copy it; do not summarise, repair, or join spans
  that are not adjacent. This field is checked against the posting and the run
  is rejected if the span is not found.
- category: one of technical, product, analytics, communication, leadership,
  domain, experience, education.
- importance: 1 to 5. Reserve 5 for demands the posting marks as required or
  repeats; give preferred or secondary demands 3 or less.
- requirement_type: must_have if the posting states the demand as required,
  preferred otherwise.

Take requirements only from what the posting says. Do not add demands that are
conventional for the role but absent from the text, do not infer seniority from
tone, and do not carry over anything from other postings. A short posting
yields few requirements, and that is the correct answer for it.

Return nothing except data conforming to the supplied schema.
"""


def build_extraction_prompt(job_description: str) -> str:
    """Place the posting after the instructions, with a clear boundary.

    The delimiter matters: the posting is untrusted input, and any instruction
    inside it is data to extract from, not a rule to follow.
    """
    return (
        f"{INSTRUCTIONS}\n"
        "----- BEGIN JOB POSTING -----\n"
        f"{job_description}\n"
        "----- END JOB POSTING -----\n"
    )
