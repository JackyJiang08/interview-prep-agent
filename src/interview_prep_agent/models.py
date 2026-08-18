"""Validated data contracts shared by every stage of the pipeline.

Each stage consumes and emits one of these models. Because every stage boundary
is validated, a bad result can be attributed to a specific stage instead of to
the system as a whole.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, NonNegativeFloat


class RequirementCategory(StrEnum):
    """The kind of capability a requirement asks for."""

    TECHNICAL = "technical"
    PRODUCT = "product"
    ANALYTICS = "analytics"
    COMMUNICATION = "communication"
    LEADERSHIP = "leadership"
    DOMAIN = "domain"
    EXPERIENCE = "experience"
    EDUCATION = "education"


class RequirementType(StrEnum):
    """Whether a posting states a requirement as mandatory or desirable."""

    MUST_HAVE = "must_have"
    PREFERRED = "preferred"


class Requirement(BaseModel):
    """A single atomic requirement lifted from a job description.

    One model serves both extraction paths. ``id``, ``text`` and ``normalized``
    are always populated; the remaining fields are populated by whichever path
    can honestly supply them, and are ``None`` otherwise rather than guessed.

    ``text`` holds the wording exactly as it appeared in the source (after only
    list-marker removal). Downstream stages may read ``normalized`` for
    comparison, but anything shown to a user must quote ``text``.

    ``source_quote`` is the span of the posting that justifies this
    requirement, and is what the grounding gate checks. Both paths set it: the
    lexical path because the requirement *is* a span of the posting, the
    model-backed path because the model is required to copy one.
    """

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    id: str = Field(pattern=r"^REQ-\d{3,}$")
    text: str = Field(min_length=1)
    normalized: str = Field(min_length=1)
    source_quote: str | None = Field(default=None, min_length=1)
    source_line: int | None = Field(default=None, ge=1)
    category: RequirementCategory | None = None
    importance: int | None = Field(default=None, ge=1, le=5)
    requirement_type: RequirementType | None = None


class RequirementExtraction(BaseModel):
    """Envelope for a model-produced requirement list.

    Exists so the response schema handed to a provider has a single named root
    object, which is what the structured-output APIs expect.
    """

    model_config = ConfigDict(extra="forbid")

    requirements: list[Requirement] = Field(default_factory=list)


class EvidenceItem(BaseModel):
    """One attested item from the candidate's evidence corpus.

    ``source`` records where the item came from — a corpus file, the resume
    section that held the bullet, or a clarification — so a citation can be
    traced past the identifier back to the document. Items minted from a
    human's answer use the ``CL-`` identifier series and carry the requirement
    they address and the question that was asked, so the traceability
    guarantee extends through the human in the loop rather than around them.
    """

    id: str = Field(pattern=r"^(?:EV|CL)-\d{3,}$")
    summary: str = Field(min_length=1)
    skills: list[str] = Field(default_factory=list)
    impact: str | None = None
    source: str | None = None
    addresses_requirement_id: str | None = Field(default=None, pattern=r"^REQ-\d{3,}$")
    question: str | None = None


class EvidenceMatch(BaseModel):
    """A scored link between one requirement and one evidence item."""

    evidence_id: str
    score: NonNegativeFloat
    overlapping_terms: list[str] = Field(default_factory=list)


class Status(StrEnum):
    """Whether a requirement is supported by the evidence corpus.

    The binary view of :data:`CoverageLevel`: every level except ``GAP``
    collapses to ``PROOF``. Kept because the plan and its committed artifacts
    speak in these terms.
    """

    PROOF = "PROOF"
    GAP = "GAP"


class CoverageLevel(StrEnum):
    """How completely the supplied evidence covers one requirement."""

    FULL = "FULL"
    PARTIAL = "PARTIAL"
    GAP = "GAP"


class RequirementMatch(BaseModel):
    """The matcher's verdict for one requirement.

    ``status`` is the degenerate binary view of ``coverage``: anything except
    a gap is proof. ``coverage``, ``explanation`` and ``confidence`` are set by
    every matcher; they are optional only so that verdicts built before these
    fields existed remain constructible, and ``None`` reads as unknown, never
    as full.
    """

    requirement_id: str
    status: Status
    matches: list[EvidenceMatch] = Field(default_factory=list)
    method: str
    coverage: CoverageLevel | None = None
    explanation: str | None = Field(default=None, min_length=1)
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)


class MatchAssessment(BaseModel):
    """One requirement's coverage as a provider is asked to report it.

    The response-schema shape for model-backed matching, converted into
    ``RequirementMatch`` immediately after validation — nothing downstream
    consumes this model. It cites evidence by identifier only, because a
    provider has no scores or term overlaps to offer, and inventing them
    here would dress model output as measurement.
    """

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    requirement_id: str
    evidence_ids: list[str] = Field(default_factory=list)
    coverage: CoverageLevel
    explanation: str = Field(min_length=1)
    confidence: float = Field(ge=0.0, le=1.0)


class MatchAssessmentList(BaseModel):
    """Envelope for a model-produced assessment list, one per requirement."""

    model_config = ConfigDict(extra="forbid")

    assessments: list[MatchAssessment] = Field(default_factory=list)


class FocusArea(BaseModel):
    """One deterministic recommendation for allocating preparation time."""

    requirement_id: str
    coverage: CoverageLevel
    priority: int = Field(ge=1, le=15)
    preparation_action: str = Field(min_length=1)
    reason: str = Field(min_length=1)


class StrategyItem(BaseModel):
    """One prioritised line of the interview strategy, tied to a requirement."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    requirement_id: str
    evidence_ids: list[str] = Field(default_factory=list)
    preparation_theme: str = Field(min_length=1)
    rationale: str = Field(min_length=1)


class StoryPlan(BaseModel):
    """One story worth rehearsing, grounded in matched evidence."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    requirement_id: str
    evidence_ids: list[str] = Field(default_factory=list)
    story_to_prepare: str = Field(min_length=1)


class RiskItem(BaseModel):
    """One exposure the interview may probe, with a mitigation."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    requirement_id: str
    risk: str = Field(min_length=1)
    mitigation: str = Field(min_length=1)


class InterviewStrategy(BaseModel):
    """The strategy layer over the focus areas.

    Doubles as the response schema for the strategy node — it is already a
    single named root object, so no envelope is needed.
    """

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    top_priorities: list[StrategyItem] = Field(default_factory=list)
    positioning_statement: str = Field(min_length=1)
    stories_to_prepare: list[StoryPlan] = Field(default_factory=list)
    risks_to_address: list[RiskItem] = Field(default_factory=list)


class MockQuestion(BaseModel):
    """One practice question, traceable to the requirement it probes."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    question: str = Field(min_length=1)
    requirement_id: str
    capability_tested: str = Field(min_length=1)
    evidence_ids: list[str] = Field(default_factory=list)
    follow_up_probe: str = Field(min_length=1)
    answer_outline: list[str] = Field(min_length=2)


class MockQuestionList(BaseModel):
    """Envelope for a model-produced question list.

    Carries no minimum length on purpose: the question floor is a package
    gate, and enforcing it in the response schema would turn a routable
    shortfall into a hard parse failure.
    """

    model_config = ConfigDict(extra="forbid")

    mock_questions: list[MockQuestion] = Field(default_factory=list)


class PrepPackage(BaseModel):
    """The validated, candidate-facing preparation product.

    Assembled only after the package gate passes, so holding one implies the
    identifier chain resolves end to end.
    """

    requirements: list[Requirement] = Field(default_factory=list)
    matches: list[RequirementMatch] = Field(default_factory=list)
    focus_areas: list[FocusArea] = Field(default_factory=list)
    strategy: InterviewStrategy
    mock_questions: list[MockQuestion] = Field(default_factory=list)


class PlanItem(BaseModel):
    """One entry in the focus plan, gap-first ordered."""

    requirement: Requirement
    status: Status
    matches: list[EvidenceMatch] = Field(default_factory=list)
    note: str


class Coverage(BaseModel):
    """Requirement accounting for the whole run."""

    total: int = Field(ge=0)
    proof: int = Field(ge=0)
    gap: int = Field(ge=0)


class FocusPlan(BaseModel):
    """Final artifact: every requirement, gaps first, each traceable."""

    coverage: Coverage
    items: list[PlanItem] = Field(default_factory=list)
    method: str


class Clarification(BaseModel):
    """One factual answer a human supplied at an interrupt.

    ``accepted_claim`` is the code-admitted restatement of the answer; when
    present it is what becomes evidence, so nothing stronger than what the
    admission gate approved can ever be cited.
    """

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    requirement_id: str = Field(pattern=r"^REQ-\d{3,}$")
    question: str = Field(min_length=1)
    answer: str = Field(min_length=1)
    accepted_claim: str | None = None


class InterviewRound(BaseModel):
    """Structured context parsed from optional freeform round text.

    Every field is optional or defaulted: the parse extracts only what the
    text states, and an absent description simply means general-purpose
    preparation. Round context influences preparation only — it changes what
    to emphasize, never what the candidate can claim.
    """

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    round_type: str | None = None
    format: str | None = None
    interviewer_roles: list[str] = Field(default_factory=list)
    focus: list[str] = Field(default_factory=list)
    notes: str | None = None


class ClarificationAssessment(BaseModel):
    """The model's structured advice about one resumed answer.

    Advice, not admission: the code-owned gate decides what becomes evidence,
    and it checks this assessment's target against the requirement actually
    asked, so model output cannot redirect evidence.
    """

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    target_requirement_id: str = Field(pattern=r"^REQ-\d{3,}$")
    is_valid: bool
    relevance_reason: str = Field(min_length=1)
    specificity_reason: str = Field(min_length=1)
    accepted_claim: str | None = None


class ClarificationRecord(BaseModel):
    """The auditable outcome for one processed gap, admitted or not."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    requirement_id: str = Field(pattern=r"^REQ-\d{3,}$")
    question: str = Field(min_length=1)
    answer: str
    assessment: ClarificationAssessment
    accepted: bool
    decision_reason: str = Field(min_length=1)
    accepted_claim: str | None = None
