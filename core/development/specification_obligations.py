"""Specification modality is independent of the existing behavior/quality kind."""
from __future__ import annotations

import re
from enum import Enum


class ObligationModality(str, Enum):
    REQUIRED = "required"
    FORBIDDEN = "forbidden"
    NON_GOAL = "non_goal"


class EvidencePolicy(str, Enum):
    BEHAVIORAL = "accepted_tests"
    DEPENDENCY = "dependency_free"
    STORAGE = "no_storage"
    PUBLIC_SURFACE = "forbidden_public_surface"
    NON_GOAL = "non_goal_scope"
    QUALITY = "static_quality"
    ENGINEERING = "engineering_policy"
    UNSUPPORTED = "unsupported_evidence_policy"


def explicit_modality(text: str) -> ObligationModality | None:
    """Recognize explicit operators, not arbitrary implementation semantics."""
    lowered = text.lower()
    non_goal = bool(re.search(r'\bnot required\b|\boptional\b|\bout of scope\b|\bno\b.+\b(?:is|are) required\b', lowered))
    forbidden = bool(re.search(r'\bmust not\b|\bshall not\b|\bdo not implement\b|\bprohibited\b|\bforbidden\b', lowered))
    if non_goal and forbidden:
        raise ValueError("ambiguous specification modality: use a narrower source quote")
    if non_goal:
        return ObligationModality.NON_GOAL
    if forbidden:
        return ObligationModality.FORBIDDEN
    return None


def grounded_modality(modality: str, source: str) -> ObligationModality:
    explicit = explicit_modality(source)
    declared = ObligationModality(modality)
    if declared == ObligationModality.NON_GOAL and explicit != declared:
        raise ValueError("non-goal requires explicit source wording")
    if explicit is not None and explicit != declared:
        raise ValueError("specification modality contradicts original source wording")
    return declared
