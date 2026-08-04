"""End-to-end smoke tests, including the quality gates."""

from __future__ import annotations

import json

import pytest

from jd_evidence_matcher import (
    EvidenceMatch,
    Requirement,
    RequirementMatch,
    Status,
    build_focus_plan,
    extract_requirements,
    run_pipeline,
)
from jd_evidence_matcher.pipeline import (
    MATCHES_ARTIFACT,
    PLAN_ARTIFACT,
    REQUIREMENTS_ARTIFACT,
)
from jd_evidence_matcher.plan import QualityGateError


def test_end_to_end_covers_every_requirement(sample_job_description, sample_evidence):
    plan = run_pipeline(sample_job_description, sample_evidence)
    expected = len(extract_requirements(sample_job_description))

    assert plan.coverage.total == expected
    assert plan.coverage.proof + plan.coverage.gap == expected
    assert len(plan.items) == expected


def test_gaps_sort_ahead_of_proven_requirements(sample_job_description, sample_evidence):
    plan = run_pipeline(sample_job_description, sample_evidence)
    statuses = [item.status for item in plan.items]
    assert statuses == sorted(statuses, key=lambda status: status is Status.PROOF)


def test_sample_yields_both_outcomes(sample_job_description, sample_evidence):
    plan = run_pipeline(sample_job_description, sample_evidence)
    assert plan.coverage.proof > 0
    assert plan.coverage.gap > 0


def test_every_citation_resolves_to_real_evidence(sample_job_description, sample_evidence):
    plan = run_pipeline(sample_job_description, sample_evidence)
    known = {item.id for item in sample_evidence}
    for item in plan.items:
        for match in item.matches:
            assert match.evidence_id in known


def test_stage_artifacts_are_written(tmp_path, sample_job_description, sample_evidence):
    run_pipeline(sample_job_description, sample_evidence, output_dir=tmp_path)

    for name in (REQUIREMENTS_ARTIFACT, MATCHES_ARTIFACT, PLAN_ARTIFACT):
        artifact = tmp_path / name
        assert artifact.is_file()
        json.loads(artifact.read_text(encoding="utf-8"))


def test_gate_rejects_citation_of_unknown_evidence(sample_evidence):
    requirement = Requirement(
        id="REQ-001", text="Own the funnel", normalized="own the funnel", source_line=1
    )
    verdict = RequirementMatch(
        requirement_id="REQ-001",
        status=Status.PROOF,
        matches=[EvidenceMatch(evidence_id="EV-999", score=0.9)],
        method="test",
    )

    with pytest.raises(QualityGateError, match="traceability"):
        build_focus_plan([requirement], [verdict], sample_evidence)


def test_gate_rejects_dropped_requirement(sample_evidence):
    requirements = [
        Requirement(id="REQ-001", text="Own the funnel", normalized="own the funnel", source_line=1),
        Requirement(id="REQ-002", text="Own the metrics", normalized="own the metrics", source_line=2),
    ]
    verdicts = [
        RequirementMatch(requirement_id="REQ-001", status=Status.GAP, matches=[], method="test")
    ]

    with pytest.raises(QualityGateError, match="coverage"):
        build_focus_plan(requirements, verdicts, sample_evidence)
