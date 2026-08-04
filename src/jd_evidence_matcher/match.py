"""Stage 2 - score each requirement against the evidence corpus.

The baseline scorer is lexical and inspectable on purpose. It reports which
terms drove every match, so a wrong verdict can be read off the output rather
than guessed at. A denser semantic scorer is a roadmap item; the ``Matcher``
signature below is the seam it would slot into.
"""

from __future__ import annotations

import math
import re
from typing import Dict, List, Sequence, Set

from .models import EvidenceItem, EvidenceMatch, Requirement, RequirementMatch, Status

METHOD_NAME = "lexical-idf-v1"

_TOKEN = re.compile(r"[a-z0-9+#]+(?:[./][a-z0-9+#]+)*")
_SPLIT_INNER = re.compile(r"[./]")

# High-frequency terms that carry no discriminating signal in a posting.
STOPWORDS = frozenset(
    {
        "a", "able", "ability", "an", "and", "any", "are", "as", "at", "be",
        "both", "build", "by", "can", "deep", "do", "etc", "experience", "for",
        "from", "good", "great", "has", "have", "help", "in", "into", "is", "it",
        "its", "must", "of", "on", "or", "our", "plus", "proven", "related",
        "solid", "strong", "such", "that", "the", "their", "them", "this", "to",
        "up", "us", "use", "used", "using", "we", "will", "with", "within",
        "work", "working", "year", "years", "you", "your",
    }
)

_MIN_TOKEN_LENGTH = 2


def _keep(token: str) -> bool:
    return len(token) >= _MIN_TOKEN_LENGTH and token not in STOPWORDS


def tokenize(text: str) -> List[str]:
    """Split text into scoring terms.

    Compound terms are kept whole *and* split, so "SQL/Python" contributes
    "sql/python", "sql" and "python" while "A/B" survives as a single term that
    its one-character parts could not represent.
    """
    tokens: List[str] = []
    for raw in _TOKEN.findall(text.lower()):
        raw = raw.strip("./")
        if not raw:
            continue
        if _keep(raw):
            tokens.append(raw)
        if _SPLIT_INNER.search(raw):
            tokens.extend(part for part in _SPLIT_INNER.split(raw) if _keep(part))
    return tokens


def _evidence_terms(item: EvidenceItem) -> Set[str]:
    parts = [item.summary, " ".join(item.skills)]
    if item.impact:
        parts.append(item.impact)
    return set(tokenize(" ".join(parts)))


def _inverse_document_frequency(
    corpus: Sequence[Set[str]],
) -> Dict[str, float]:
    """Weight terms by how few evidence items contain them."""
    total = len(corpus)
    document_frequency: Dict[str, int] = {}
    for terms in corpus:
        for term in terms:
            document_frequency[term] = document_frequency.get(term, 0) + 1
    return {
        term: math.log(1.0 + total / (1.0 + count))
        for term, count in document_frequency.items()
    }


def _default_weight(total: int) -> float:
    """Weight for a requirement term absent from every evidence item."""
    return math.log(1.0 + total / 1.0)


def score_requirement(
    requirement: Requirement,
    evidence_terms: Sequence[Set[str]],
    weights: Dict[str, float],
    default_weight: float,
) -> List[float]:
    """Return the coverage score of ``requirement`` against each evidence item.

    A score is the share of the requirement's weighted terms that the evidence
    item attests, so it reads directly as "how much of this requirement is
    actually backed up", and stays in [0, 1].
    """
    terms = set(tokenize(requirement.text))
    if not terms:
        return [0.0] * len(evidence_terms)

    weighted = {term: weights.get(term, default_weight) for term in terms}
    denominator = sum(weighted.values())
    if denominator <= 0:
        return [0.0] * len(evidence_terms)

    scores = []
    for item_terms in evidence_terms:
        overlap = terms & item_terms
        scores.append(sum(weighted[term] for term in overlap) / denominator)
    return scores


def match_requirements(
    requirements: Sequence[Requirement],
    evidence: Sequence[EvidenceItem],
    threshold: float,
    max_matches: int,
) -> List[RequirementMatch]:
    """Label every requirement PROOF or GAP against the evidence corpus.

    Args:
        requirements: Output of the extraction stage.
        evidence: The candidate's evidence corpus.
        threshold: Minimum score for a requirement to count as supported.
        max_matches: Cap on evidence items reported per requirement.

    Returns:
        One verdict per requirement, in the input order.
    """
    corpus = [_evidence_terms(item) for item in evidence]
    weights = _inverse_document_frequency(corpus)
    default_weight = _default_weight(len(corpus))

    verdicts: List[RequirementMatch] = []
    for requirement in requirements:
        scores = score_requirement(requirement, corpus, weights, default_weight)
        terms = set(tokenize(requirement.text))

        ranked = sorted(
            (
                EvidenceMatch(
                    evidence_id=evidence[index].id,
                    score=round(score, 4),
                    overlapping_terms=sorted(terms & corpus[index]),
                )
                for index, score in enumerate(scores)
                if score >= threshold
            ),
            key=lambda match: match.score,
            reverse=True,
        )[:max_matches]

        verdicts.append(
            RequirementMatch(
                requirement_id=requirement.id,
                status=Status.PROOF if ranked else Status.GAP,
                matches=ranked,
                method=METHOD_NAME,
            )
        )

    return verdicts
