"""Deterministic checks that guard every stage boundary.

Two kinds of caller need these checks, so each one is exposed twice:

* ``collect_*`` returns a list of error strings and decides nothing. The graph
  uses this form, because a routing predicate has to be a pure function.
* ``check_*`` raises ``QualityGateError``. Direct callers use this form,
  which is the behaviour the pipeline has always had — a violated guarantee
  stops the run rather than returning a plan nobody should trust.

Both forms share one implementation, so the two paths can never disagree about
what counts as valid.
"""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Sequence

from ..models import (
    CoverageLevel,
    EvidenceItem,
    FocusArea,
    InterviewStrategy,
    MockQuestion,
    Requirement,
    RequirementMatch,
    ResearchFinding,
    ResearchSourceKind,
    Status,
)

_WHITESPACE = re.compile(r"\s+")


class QualityGateError(ValueError):
    """Raised when an artifact violates a stated guarantee of the pipeline."""


def fold(text: str) -> str:
    """Reduce text to the form used for grounding comparisons.

    Whitespace is collapsed and case is folded, so a quote that differs from
    the posting only in wrapping or capitalisation still counts as grounded.
    Nothing else is altered: a quote that drops or adds words does not match.
    """
    return _WHITESPACE.sub(" ", text).strip().casefold()


def collect_requirement_errors(
    job_description: str,
    requirements: Sequence[Requirement],
    min_requirements: int = 1,
    max_requirements: int = 50,
) -> list[str]:
    """Check an extracted requirement set against the posting it came from.

    Applies four checks, in the order a reader would want them reported:
    plausible count, unique and sequential identifiers, unique statements, and
    grounding of every source quote in the posting.

    Args:
        job_description: The posting the requirements were extracted from.
        requirements: The extracted set, in the order produced.
        min_requirements: Fewest requirements a run may produce.
        max_requirements: Most requirements a run may produce.

    Returns:
        Human-readable errors, empty when the set is valid.
    """
    errors: list[str] = []
    count = len(requirements)

    if count < min_requirements or count > max_requirements:
        errors.append(
            f"coverage: expected between {min_requirements} and "
            f"{max_requirements} requirements, received {count}"
        )

    identifiers = [item.id for item in requirements]
    if len(set(identifiers)) != len(identifiers):
        errors.append("identity: requirement identifiers must be unique")
    else:
        expected = [f"REQ-{index:03d}" for index in range(1, count + 1)]
        if identifiers and identifiers != expected:
            errors.append(
                "identity: requirement identifiers must run sequentially "
                "from REQ-001 in source order"
            )

    statements = [fold(item.normalized) for item in requirements]
    if len(set(statements)) != len(statements):
        errors.append("identity: requirement statements must be unique")

    folded_posting = fold(job_description)
    for item in requirements:
        if item.source_quote is None:
            errors.append(f"grounding: {item.id} carries no source quote")
        elif fold(item.source_quote) not in folded_posting:
            errors.append(
                f"grounding: {item.id} source quote does not appear in the job description"
            )

    return errors


def check_requirements(
    job_description: str,
    requirements: Sequence[Requirement],
    min_requirements: int = 1,
    max_requirements: int = 50,
) -> None:
    """Raise if an extracted requirement set fails any check.

    Raises:
        QualityGateError: With every failure listed, not just the first.
    """
    errors = collect_requirement_errors(
        job_description, requirements, min_requirements, max_requirements
    )
    if errors:
        raise QualityGateError("; ".join(errors))


def collect_match_errors(
    requirements: Sequence[Requirement],
    verdicts: Sequence[RequirementMatch],
    evidence: Sequence[EvidenceItem],
) -> list[str]:
    """Check a matcher's verdict set, whichever matcher produced it.

    Four guarantees: every requirement is matched exactly once and nothing
    else is; verdicts follow the requirements' order; every cited evidence
    identifier exists in the corpus; and a verdict's coverage agrees with its
    citations — a gap cites nothing, anything else cites at least one item.
    """
    errors: list[str] = []

    requirement_ids = [item.id for item in requirements]
    verdict_ids = [item.requirement_id for item in verdicts]
    verdict_id_set = set(verdict_ids)

    counts = Counter(verdict_ids)
    duplicates = sorted(identifier for identifier, count in counts.items() if count > 1)
    if duplicates:
        errors.append(f"identity: requirements matched more than once: {', '.join(duplicates)}")

    missing = sorted(set(requirement_ids) - verdict_id_set)
    if missing:
        errors.append(f"coverage: requirements never matched: {', '.join(missing)}")

    unknown = sorted(verdict_id_set - set(requirement_ids))
    if unknown:
        errors.append(f"coverage: verdicts for unknown requirements: {', '.join(unknown)}")

    if not missing and not unknown and len(verdict_id_set) == len(verdict_ids):
        if verdict_ids != requirement_ids:
            errors.append("identity: verdicts must follow the requirements' order")

    known_evidence = {item.id for item in evidence}
    for verdict in verdicts:
        cited = [match.evidence_id for match in verdict.matches]
        unknown_cited = sorted(set(cited) - known_evidence)
        if unknown_cited:
            errors.append(
                f"traceability: {verdict.requirement_id} cites "
                f"unknown evidence {', '.join(unknown_cited)}"
            )
        if len(set(cited)) != len(cited):
            errors.append(f"traceability: {verdict.requirement_id} cites evidence twice")

        if verdict.coverage is CoverageLevel.GAP and cited:
            errors.append(f"grounding: {verdict.requirement_id} is GAP and must not cite evidence")
        if verdict.coverage in (CoverageLevel.FULL, CoverageLevel.PARTIAL) and not cited:
            errors.append(
                f"grounding: {verdict.requirement_id} is {verdict.coverage.value} "
                "with no supporting evidence"
            )

    return errors


def check_matches(
    requirements: Sequence[Requirement],
    verdicts: Sequence[RequirementMatch],
    evidence: Sequence[EvidenceItem],
) -> None:
    """Raise if a matcher's verdict set fails any check.

    Raises:
        QualityGateError: With every failure listed, not just the first.
    """
    errors = collect_match_errors(requirements, verdicts, evidence)
    if errors:
        raise QualityGateError("; ".join(errors))


def collect_plan_errors(
    requirements: Sequence[Requirement],
    verdicts: Sequence[RequirementMatch],
    evidence: Sequence[EvidenceItem],
) -> list[str]:
    """Check that matching neither lost nor invented anything.

    Coverage compares the identifier sets on both sides. Traceability confirms
    every citation resolves to a real evidence item, and that nothing is marked
    supported without citing anything at all.
    """
    errors: list[str] = []

    requirement_ids = [item.id for item in requirements]
    verdict_ids = [item.requirement_id for item in verdicts]

    if len(set(requirement_ids)) != len(requirement_ids):
        errors.append("coverage: duplicate requirement identifiers")

    if set(requirement_ids) != set(verdict_ids):
        missing = sorted(set(requirement_ids) - set(verdict_ids))
        invented = sorted(set(verdict_ids) - set(requirement_ids))
        errors.append(f"coverage: dropped={missing or 'none'} invented={invented or 'none'}")

    known_evidence = {item.id for item in evidence}
    for verdict in verdicts:
        for match in verdict.matches:
            if match.evidence_id not in known_evidence:
                errors.append(
                    f"traceability: {verdict.requirement_id} cites "
                    f"unknown evidence {match.evidence_id}"
                )
        if verdict.status is Status.PROOF and not verdict.matches:
            errors.append(
                f"traceability: {verdict.requirement_id} is PROOF with no supporting evidence"
            )

    return errors


def check_plan(
    requirements: Sequence[Requirement],
    verdicts: Sequence[RequirementMatch],
    evidence: Sequence[EvidenceItem],
) -> None:
    """Raise if matching lost, invented, or mis-cited anything.

    Raises:
        QualityGateError: With every failure listed, not just the first.
    """
    errors = collect_plan_errors(requirements, verdicts, evidence)
    if errors:
        raise QualityGateError("; ".join(errors))


def _reference_errors(
    section: str,
    items,
    requirement_ids: set[str],
    evidence_by_requirement: dict[str, tuple[CoverageLevel, set[str]]],
) -> list[str]:
    """Shared checks for anything downstream that cites identifiers.

    Every item must name a known requirement; an item for a GAP requirement
    must cite no evidence; anything else must cite at least one identifier,
    all of them drawn from the evidence matched to that requirement.
    """
    errors: list[str] = []
    for item in items:
        label = f"{section} for {item.requirement_id}"
        if item.requirement_id not in requirement_ids:
            errors.append(
                f"traceability: {section} references unknown requirement {item.requirement_id}"
            )
            continue

        if not hasattr(item, "evidence_ids"):
            continue
        coverage, matched = evidence_by_requirement[item.requirement_id]
        cited = set(item.evidence_ids)
        if coverage is CoverageLevel.GAP:
            if cited:
                errors.append(f"grounding: {label} must not cite evidence for a gap")
            continue
        if not cited:
            errors.append(f"grounding: {label} must retain at least one matched evidence id")
            continue
        stray = sorted(cited - matched)
        if stray:
            errors.append(
                f"traceability: {label} cites evidence not matched to the "
                f"requirement: {', '.join(stray)}"
            )
    return errors


def _evidence_by_requirement(
    verdicts: Sequence[RequirementMatch],
) -> dict[str, tuple[CoverageLevel, set[str]]]:
    table: dict[str, tuple[CoverageLevel, set[str]]] = {}
    for verdict in verdicts:
        coverage = verdict.coverage or (
            CoverageLevel.GAP if verdict.status is Status.GAP else CoverageLevel.FULL
        )
        table[verdict.requirement_id] = (
            coverage,
            {match.evidence_id for match in verdict.matches},
        )
    return table


def collect_strategy_errors(
    requirements: Sequence[Requirement],
    verdicts: Sequence[RequirementMatch],
    focus_areas: Sequence[FocusArea],
    strategy: InterviewStrategy,
) -> list[str]:
    """Check the strategy against the state it was composed from.

    References must resolve, evidence links must stay inside each
    requirement's matched evidence, and every focus area at GAP coverage must
    appear in the risks — a gap left out of the risks is a gap the candidate
    walks into unprepared.
    """
    requirement_ids = {item.id for item in requirements}
    table = _evidence_by_requirement(verdicts)

    errors = _reference_errors("strategy item", strategy.top_priorities, requirement_ids, table)
    errors += _reference_errors("story plan", strategy.stories_to_prepare, requirement_ids, table)
    errors += _reference_errors("risk", strategy.risks_to_address, requirement_ids, table)

    risk_ids = {item.requirement_id for item in strategy.risks_to_address}
    for area in focus_areas:
        if area.coverage is CoverageLevel.GAP and area.requirement_id not in risk_ids:
            errors.append(
                f"coverage: gap focus area {area.requirement_id} "
                "does not appear in risks_to_address"
            )
    return errors


def check_strategy(
    requirements: Sequence[Requirement],
    verdicts: Sequence[RequirementMatch],
    focus_areas: Sequence[FocusArea],
    strategy: InterviewStrategy,
) -> None:
    """Raise if the strategy fails any check.

    Raises:
        QualityGateError: With every failure listed, not just the first.
    """
    errors = collect_strategy_errors(requirements, verdicts, focus_areas, strategy)
    if errors:
        raise QualityGateError("; ".join(errors))


def collect_question_errors(
    requirements: Sequence[Requirement],
    verdicts: Sequence[RequirementMatch],
    questions: Sequence[MockQuestion],
    min_questions: int = 8,
) -> list[str]:
    """Check the question set against the state it was generated from."""
    errors: list[str] = []
    if len(questions) < min_questions:
        errors.append(
            f"coverage: expected at least {min_questions} practice questions, "
            f"received {len(questions)}"
        )
    requirement_ids = {item.id for item in requirements}
    errors += _reference_errors(
        "question", questions, requirement_ids, _evidence_by_requirement(verdicts)
    )
    return errors


def check_questions(
    requirements: Sequence[Requirement],
    verdicts: Sequence[RequirementMatch],
    questions: Sequence[MockQuestion],
    min_questions: int = 8,
) -> None:
    """Raise if the question set fails any check.

    Raises:
        QualityGateError: With every failure listed, not just the first.
    """
    errors = collect_question_errors(requirements, verdicts, questions, min_questions)
    if errors:
        raise QualityGateError("; ".join(errors))


def collect_package_errors(
    job_description: str,
    evidence: Sequence[EvidenceItem],
    requirements: Sequence[Requirement],
    verdicts: Sequence[RequirementMatch],
    focus_areas: Sequence[FocusArea],
    strategy: InterviewStrategy | None,
    questions: Sequence[MockQuestion],
    min_questions: int = 8,
    research_findings: Sequence[ResearchFinding] = (),
    max_research_findings: int = 12,
) -> list[str]:
    """Run the full deterministic invariant set over a candidate package.

    Composes every stage gate and adds the package-level invariants: all
    sections present, one focus area per requirement with coverage agreeing
    with the verdict, and the identifier chain resolving end to end through
    strategy and questions.
    """
    errors: list[str] = []

    if not requirements:
        errors.append("coverage: the package has no requirements")
    if not evidence:
        errors.append("coverage: the package has no evidence")
    if strategy is None:
        errors.append("coverage: the package has no strategy")

    errors += collect_requirement_errors(job_description, requirements)
    errors += collect_match_errors(requirements, verdicts, evidence)

    for verdict in verdicts:
        if verdict.coverage is None:
            errors.append(f"coverage: {verdict.requirement_id} carries no explicit coverage level")

    requirement_ids = [item.id for item in requirements]
    focus_ids = [area.requirement_id for area in focus_areas]
    focus_counts = Counter(focus_ids)
    for identifier in sorted(set(requirement_ids) - set(focus_ids)):
        errors.append(f"coverage: no focus area for {identifier}")
    for identifier, count in sorted(focus_counts.items()):
        if count > 1:
            errors.append(f"identity: duplicate focus area for {identifier}")
        if identifier not in set(requirement_ids):
            errors.append(f"traceability: focus area references unknown requirement {identifier}")

    verdict_by_id = {verdict.requirement_id: verdict for verdict in verdicts}
    for area in focus_areas:
        verdict = verdict_by_id.get(area.requirement_id)
        if (
            verdict is not None
            and verdict.coverage is not None
            and area.coverage is not verdict.coverage
        ):
            errors.append(
                f"identity: focus area {area.requirement_id} coverage "
                "disagrees with the match verdict"
            )

    if strategy is not None:
        errors += collect_strategy_errors(requirements, verdicts, focus_areas, strategy)
    errors += collect_question_errors(requirements, verdicts, questions, min_questions)
    errors += collect_research_errors(research_findings, max_research_findings)
    errors += _research_citation_errors(strategy, questions, research_findings)

    return errors


def check_package(
    job_description: str,
    evidence: Sequence[EvidenceItem],
    requirements: Sequence[Requirement],
    verdicts: Sequence[RequirementMatch],
    focus_areas: Sequence[FocusArea],
    strategy: InterviewStrategy | None,
    questions: Sequence[MockQuestion],
    min_questions: int = 8,
) -> None:
    """Raise if the package fails any invariant.

    Raises:
        QualityGateError: With every failure listed, not just the first.
    """
    errors = collect_package_errors(
        job_description,
        evidence,
        requirements,
        verdicts,
        focus_areas,
        strategy,
        questions,
        min_questions,
    )
    if errors:
        raise QualityGateError("; ".join(errors))


_SRC_TOKEN = re.compile(r"\bSRC-\d{3,}\b")


def collect_research_errors(
    findings: Sequence[ResearchFinding],
    max_findings: int = 12,
) -> list[str]:
    """Check a minted finding set.

    Identifiers must run sequentially from SRC-001 and be unique, search
    findings must carry the URL they came from, and the count must respect
    the configured cap.
    """
    errors: list[str] = []
    if len(findings) > max_findings:
        errors.append(
            f"coverage: expected at most {max_findings} research findings, received {len(findings)}"
        )
    identifiers = [item.finding_id for item in findings]
    if len(set(identifiers)) != len(identifiers):
        errors.append("identity: research finding identifiers must be unique")
    else:
        expected = [f"SRC-{index:03d}" for index in range(1, len(findings) + 1)]
        if identifiers and identifiers != expected:
            errors.append(
                "identity: research finding identifiers must run sequentially from SRC-001"
            )
    for item in findings:
        if item.source_kind is ResearchSourceKind.SEARCH and not item.url:
            errors.append(
                f"grounding: {item.finding_id} came from search and must carry its source url"
            )
    return errors


def check_research(findings: Sequence[ResearchFinding], max_findings: int = 12) -> None:
    """Raise if a finding set fails any check.

    Raises:
        QualityGateError: With every failure listed, not just the first.
    """
    errors = collect_research_errors(findings, max_findings)
    if errors:
        raise QualityGateError("; ".join(errors))


def _research_citation_errors(
    strategy: InterviewStrategy | None,
    questions: Sequence[MockQuestion],
    findings: Sequence[ResearchFinding],
) -> list[str]:
    """Resolve every SRC- token cited in preparation text.

    Findings may be cited inline in strategy and question prose; each cited
    identifier must resolve to a minted finding. Citations *as evidence* need
    no check here - a finding identifier in an evidence list already fails
    the match and package gates, because findings are never in the corpus.
    """
    known = {item.finding_id for item in findings}
    texts: list[tuple[str, str]] = []
    if strategy is not None:
        texts.append(("strategy positioning", strategy.positioning_statement))
        for item in strategy.top_priorities:
            texts.append((f"strategy item for {item.requirement_id}", item.rationale))
            texts.append((f"strategy item for {item.requirement_id}", item.preparation_theme))
        for story in strategy.stories_to_prepare:
            texts.append((f"story plan for {story.requirement_id}", story.story_to_prepare))
        for risk in strategy.risks_to_address:
            texts.append((f"risk for {risk.requirement_id}", risk.risk))
            texts.append((f"risk for {risk.requirement_id}", risk.mitigation))
    for question in questions:
        texts.append((f"question for {question.requirement_id}", question.question))
        texts.append((f"question for {question.requirement_id}", question.follow_up_probe))
        for line in question.answer_outline:
            texts.append((f"question for {question.requirement_id}", line))

    errors: list[str] = []
    reported: set[tuple[str, str]] = set()
    for label, text in texts:
        for token in _SRC_TOKEN.findall(text):
            if token not in known and (label, token) not in reported:
                reported.add((label, token))
                errors.append(f"traceability: {label} cites unknown research {token}")
    return errors
