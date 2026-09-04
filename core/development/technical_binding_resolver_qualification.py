"""Frozen contract and fixtures for TechnicalBindingResolver qualification."""
from __future__ import annotations

import json
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path

from core.development.technical_binding_resolver import (
    InheritedTechnicalBindingConstraint,
    TechnicalBinding,
    TechnicalBindingBehavior,
    TechnicalBindingComponentContext,
    TechnicalBindingResolutionRequest,
    TechnicalBindingResolutionStatus,
    TechnicalBindingRole,
    TechnicalCandidate,
    output_schema_signature,
)

CONTRACT_VERSION = "technical-binding-resolver-v1"
FIXTURE_PATH = Path("tests/fixtures/technical_binding_resolver_v1.json")
LOCAL_REASONING_CONFIGURATION = {
    "required_capabilities": ["reasoning", "coding"], "complexity": "medium",
    "provider_path": "provider-neutral-local-primary", "local_only": True,
    "cloud_fallback": False, "semantic_requests_per_resolution": 1,
    "format_only_repair_maximum": 1,
}
QUALIFICATION_MATRIX = (
    "R1-1", "R2-1", "R3-1", "R4-1", "R1-2", "R2-2", "R3-2", "R4-2", "R1-3", "R2-3", "R3-3", "R4-3",
)

@dataclass(frozen=True)
class ExpectedTechnicalBindingJudgment:
    status: TechnicalBindingResolutionStatus
    bindings: tuple[TechnicalBinding, ...]

@dataclass(frozen=True)
class TechnicalBindingQualificationFixture:
    fixture_id: str
    request: TechnicalBindingResolutionRequest
    expected: ExpectedTechnicalBindingJudgment

def load_fixtures(repository_root: Path) -> dict[str, TechnicalBindingQualificationFixture]:
    source = repository_root / FIXTURE_PATH
    payload = json.loads(source.read_text(encoding="utf-8"))
    fixtures = [_fixture(item) for item in payload["fixtures"]]
    result = {fixture.fixture_id: fixture for fixture in fixtures}
    if tuple(result) != ("R1", "R2", "R3", "R4") or len(result) != 4:
        raise ValueError("technical binding qualification requires exactly frozen R1-R4 fixtures")
    return result

def fixture_bytes(repository_root: Path) -> bytes:
    return (repository_root / FIXTURE_PATH).read_bytes()

def qualification_contract_signature(repository_root: Path, configured_model: str) -> str:
    payload = {
        "version": CONTRACT_VERSION, "output_schema_signature": output_schema_signature(),
        "fixture_sha256": sha256(fixture_bytes(repository_root)).hexdigest(),
        "local_reasoning_configuration": LOCAL_REASONING_CONFIGURATION,
        "configured_model": configured_model, "qualification_matrix": QUALIFICATION_MATRIX,
    }
    return sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()

def _fixture(item: object) -> TechnicalBindingQualificationFixture:
    if not isinstance(item, dict):
        raise ValueError("fixture must be an object")
    request_payload = _object(item, "request")
    behavior_payload = _object(request_payload, "behavior")
    behavior = TechnicalBindingBehavior(
        _text(behavior_payload, "ref"), _text(behavior_payload, "summary"), _text(behavior_payload, "observable_outcome"),
        _strings(behavior_payload.get("source_refs", [])), _pairs(behavior_payload.get("source_clauses", [])),
    )
    candidates_payload = _list(request_payload, "technical_candidates")
    candidates = tuple(_candidate(candidate) for candidate in candidates_payload)
    context_payload = request_payload.get("component_context")
    context = None if context_payload is None else TechnicalBindingComponentContext(
        _text(_as_object(context_payload), "component_name"), _pairs(_as_object(context_payload).get("source_excerpts", []))
    )
    constraints = tuple(_constraint(constraint) for constraint in _optional_list(request_payload, "inherited_constraints"))
    expected_payload = _object(item, "expected")
    expected = ExpectedTechnicalBindingJudgment(
        TechnicalBindingResolutionStatus(_text(expected_payload, "status")),
        tuple(_binding(binding) for binding in _list(expected_payload, "bindings")),
    )
    return TechnicalBindingQualificationFixture(
        _text(item, "fixture_id"), TechnicalBindingResolutionRequest(behavior, candidates, context, constraints), expected
    )

def _candidate(value: object) -> TechnicalCandidate:
    item = _as_object(value)
    evidence = item.get("repository_evidence")
    if evidence is not None and not isinstance(evidence, str):
        raise ValueError("fixture repository evidence must be text")
    return TechnicalCandidate(_text(item, "technical_ref"), _text(item, "kind"), _text(item, "qualified_identifier"), _text(item, "origin"), evidence, _strings(item.get("evidence_refs", [])))

def _constraint(value: object) -> InheritedTechnicalBindingConstraint:
    item = _as_object(value)
    role = item.get("role")
    rationale = item.get("rationale", "")
    if role is not None and not isinstance(role, str):
        raise ValueError("fixture inherited role must be text")
    if not isinstance(rationale, str):
        raise ValueError("fixture inherited rationale must be text")
    return InheritedTechnicalBindingConstraint(_text(item, "technical_ref"), TechnicalBindingRole(role) if role else None, rationale)

def _binding(value: object) -> TechnicalBinding:
    item = _as_object(value)
    return TechnicalBinding(_text(item, "technical_ref"), TechnicalBindingRole(_text(item, "role")))

def _object(value: dict[str, object], key: str) -> dict[str, object]:
    return _as_object(value.get(key))

def _as_object(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ValueError("fixture object is invalid")
    return value

def _list(value: dict[str, object], key: str) -> list[object]:
    result = value.get(key)
    if not isinstance(result, list):
        raise ValueError("fixture list is invalid")
    return result

def _optional_list(value: dict[str, object], key: str) -> list[object]:
    candidate = value.get(key, [])
    if not isinstance(candidate, list):
        raise ValueError("fixture optional list is invalid")
    return candidate

def _text(value: dict[str, object], key: str) -> str:
    result = value.get(key)
    if not isinstance(result, str):
        raise ValueError(f"fixture {key} must be text")
    return result

def _strings(value: object) -> tuple[str, ...]:
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise ValueError("fixture string collection is invalid")
    return tuple(value)

def _pairs(value: object) -> tuple[tuple[str, str], ...]:
    if not isinstance(value, list):
        raise ValueError("fixture evidence collection is invalid")
    return tuple((_text(_as_object(item), "ref"), _text(_as_object(item), "text")) for item in value)
