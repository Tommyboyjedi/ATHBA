"""Frozen v3 qualification contract and subset-selection fixtures."""
from __future__ import annotations

import json
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path

from core.development.technical_binding_resolver_v3 import (
    TechnicalBindingBehaviorV3,
    TechnicalBindingSelectionRequestV3,
    TechnicalCandidateV3,
    selection_schema_signature,
)

CONTRACT_VERSION = "technical-binding-resolver-v3"
FIXTURE_PATH = Path("tests/fixtures/technical_binding_resolver_v3.json")
MATRIX = ("R1-1", "R2-1", "R3-1", "R4-1", "R1-2", "R2-2", "R3-2", "R4-2", "R1-3", "R2-3", "R3-3", "R4-3")
LOCAL_REASONING_CONFIGURATION = {
    "required_capabilities": ["reasoning", "coding"],
    "complexity": "medium",
    "provider_path": "provider-neutral-local-primary",
    "local_only": True,
    "cloud_fallback": False,
    "semantic_requests_per_resolution": 1,
    "format_only_repair_maximum": 1,
}


@dataclass(frozen=True)
class TechnicalBindingV3QualificationFixture:
    fixture_id: str
    request: TechnicalBindingSelectionRequestV3
    expected_selected_refs: tuple[str, ...]


def load_fixtures(repository_root: Path) -> dict[str, TechnicalBindingV3QualificationFixture]:
    payload = json.loads((repository_root / FIXTURE_PATH).read_text(encoding="utf-8"))
    fixtures = tuple(_fixture(item) for item in payload["fixtures"])
    result = {fixture.fixture_id: fixture for fixture in fixtures}
    if tuple(result) != ("R1", "R2", "R3", "R4") or len(result) != 4:
        raise ValueError("v3 qualification requires exactly frozen R1-R4 fixtures")
    return result


def expected_results(repository_root: Path) -> dict[str, tuple[str, ...]]:
    return {fixture_id: fixture.expected_selected_refs for fixture_id, fixture in load_fixtures(repository_root).items()}


def qualification_contract_signature(repository_root: Path, configured_model: str) -> str:
    payload = {
        "version": CONTRACT_VERSION,
        "schema_signature": selection_schema_signature(),
        "fixture_sha256": sha256((repository_root / FIXTURE_PATH).read_bytes()).hexdigest(),
        "expected": expected_results(repository_root),
        "matrix": MATRIX,
        "configuration": LOCAL_REASONING_CONFIGURATION,
        "model": configured_model,
    }
    return sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def _fixture(item: object) -> TechnicalBindingV3QualificationFixture:
    if not isinstance(item, dict):
        raise ValueError("fixture must be an object")
    behavior_payload = _object(item, "behavior")
    behavior = TechnicalBindingBehaviorV3(
        _text(behavior_payload, "behavior_ref"),
        _text(behavior_payload, "summary"),
        _text(behavior_payload, "observable_outcome"),
    )
    candidates = tuple(
        TechnicalCandidateV3(_text(_as_object(candidate), "technical_ref"), _text(_as_object(candidate), "qualified_identifier"))
        for candidate in _list(item, "candidates")
    )
    request = TechnicalBindingSelectionRequestV3(behavior, candidates, tuple(_strings(item.get("inherited_mandatory_refs", []))))
    return TechnicalBindingV3QualificationFixture(_text(item, "fixture_id"), request, tuple(_strings(item.get("expected_selected_refs", []))))


def _object(payload: dict[str, object], key: str) -> dict[str, object]:
    return _as_object(payload.get(key))


def _as_object(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ValueError("fixture object is invalid")
    return value


def _list(payload: dict[str, object], key: str) -> list[object]:
    value = payload.get(key)
    if not isinstance(value, list):
        raise ValueError("fixture list is invalid")
    return value


def _text(payload: dict[str, object], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str):
        raise ValueError(f"fixture {key} must be text")
    return value


def _strings(value: object) -> list[str]:
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise ValueError("fixture string collection is invalid")
    return value
