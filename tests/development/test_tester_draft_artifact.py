"""Standalone current-behavior authoring, independent of accumulated tests."""
import json
import subprocess
from dataclasses import replace
from types import SimpleNamespace

import pytest

from core.development.microcycle_domain import FinalTestMaterialisationRequest
from core.development.python_pytest_adapter import PythonPytestAdapter
from core.development.scenario_drafting import (
    GitCandidateScenarioSourceReader, ScenarioDraftWorkUnitFactory,
    ScenarioDraftWorkUnitRequest,
)
from core.development.scenario_drafting_domain import ScenarioDraftRunState
from core.development.specification_domain import SourceRequirementClause
from core.development.strict_microcycle import FrontierCandidateRequest, GitFrontierMaterialiser
from core.development.strict_tdd_feature_execution_advance import _scenario_draft_request
from core.development.tester_artifact import draft_artifact_path, selected_source_payload
from tests.development.test_scenario_drafting import (
    accepted, approval, binding, candidate, components, request, MemoryStateStore,
)


def isolated_request():
    value = request("catalog")
    return replace(value, draft_artifact_path=draft_artifact_path(value.scenario_id, value.allowed_test_path))


def unit_for(value):
    return ScenarioDraftWorkUnitFactory().build(ScenarioDraftWorkUnitRequest(value, 1, None))


def test_authoring_scope_is_a_standalone_identity_owned_artifact():
    value = isolated_request()
    unit = unit_for(value)
    assert unit.allowed_paths == [value.authoring_path]
    assert value.allowed_test_path not in unit.allowed_paths
    assert unit.acceptance.required_artifacts == [value.authoring_path]
    assert unit.acceptance.commands[0][-1] == value.authoring_path
    payload = json.loads(unit.objective)
    assert payload["allowed_test_path"] == value.authoring_path
    assert payload["ticket"]["planned_canonical_test_identity"] == value.ticket.test_name
    assert "bounded tests" not in unit.objective
    assert "bounded production" not in unit.objective


@pytest.mark.parametrize("path", ["catalog.py", "tests/test_catalog.py",
    ".athba/scenario-drafts/another/test_catalog.py"])
def test_unowned_draft_path_is_rejected(path):
    with pytest.raises(ValueError, match="draft artifact"):
        replace(request("catalog"), draft_artifact_path=path)


def test_selected_source_excerpt_excludes_future_operations_but_durable_quote_survives():
    clause = SourceRequirementClause(
        "SRC-CATALOG", "catalog.add(name) records the item.", "behavior",
        source_quote="catalog.add(name) records the item. A future remove(name) removes it.",
        subject="catalog.add(name) records the item.",
    )
    value = replace(isolated_request(), source_requirement_evidence=(clause,))
    payload = json.loads(unit_for(value).objective)
    assert payload["source_requirements"] == [selected_source_payload(clause)]
    assert "remove(name)" not in unit_for(value).objective
    assert "remove(name)" in clause.to_dict()["source_quote"]


def test_legacy_selected_clause_does_not_duplicate_its_text_as_excerpt():
    clause = SourceRequirementClause("SRC-CATALOG", "catalog.add(name) records the item.", "behavior")
    assert "source_excerpt" not in selected_source_payload(clause)


@pytest.mark.asyncio
async def test_approval_reads_artifact_then_freezes_canonical_test_identity():
    value = isolated_request()
    service, gateway, reasoning, reader = components(
        [accepted("catalog-ticket--scenario-draft-1", "b" * 40, "draft")],
        [approval("SRC-CATALOG")], {"b" * 40: candidate("catalog")},
    )
    result = await service.draft(value, binding())
    assert result.approved
    assert reader.calls == [("b" * 40, value.authoring_path)]
    assert result.state.draft_artifact_path == value.authoring_path
    assert ScenarioDraftRunState.from_dict(result.state.to_dict()) == result.state
    assert result.state.approved_microcycle.scenario_draft.test_path == value.allowed_test_path
    assert result.state.approved_microcycle.scenario_draft.canonical_test_identity == value.ticket.test_name
    assert "catalog.py" not in gateway.calls[0][0].allowed_paths


@pytest.mark.asyncio
async def test_repair_keeps_artifact_and_own_candidate_without_future_source():
    clause = SourceRequirementClause(
        "SRC-CATALOG", "catalog.add(name) records the item.", "behavior",
        source_quote="catalog.add(name) records the item. A future remove(name) removes it.",
        subject="catalog.add(name) records the item.",
    )
    value = replace(isolated_request(), source_requirement_evidence=(clause,))
    malformed = candidate("catalog") + "\ndef test_extra():\n    assert True\n"
    service, gateway, reasoning, reader = components(
        [accepted("catalog-ticket--scenario-draft-1", "b" * 40, "first"),
         accepted("catalog-ticket--scenario-draft-2", "c" * 40, "second")],
        [approval("SRC-CATALOG")], {"b" * 40: malformed, "c" * 40: candidate("catalog")},
    )
    first = await service.draft(value, binding())
    assert not first.approved
    result = await service.draft(value, binding())
    assert result.approved and len(result.state.attempts) == 2
    payload = json.loads(gateway.calls[1][0].objective)
    assert payload["previous_candidate"]["source"] == malformed
    assert payload["repair_feedback"]
    assert "remove(name)" not in gateway.calls[1][0].objective
    assert all(unit.allowed_paths == [value.authoring_path] for unit, _ in gateway.calls)
    # Independent semantic review retains original source authority.
    assert json.loads(reasoning.requests[0].prompt)["source_requirements"] == [clause.to_dict()]


def test_production_builder_uses_new_artifact_but_resumes_legacy_path(monkeypatch):
    import core.development.strict_tdd_feature_execution_advance as advance
    value = request("catalog")
    behavior = SimpleNamespace(source_refs=("SRC-CATALOG",))
    feature = SimpleNamespace(behavior=behavior, contract=SimpleNamespace(source_clauses=()),
        project=SimpleNamespace(repository_root="/tmp/unused"), canonical_development_base="a" * 40)
    monkeypatch.setattr(advance, "_ticket_for", lambda _request: value.ticket)
    monkeypatch.setattr(advance, "_facts", lambda *_args: value.repository_facts)
    monkeypatch.setattr(advance, "_source_requirement_evidence", lambda _request: ())
    monkeypatch.setattr(advance, "_semantic_annotations", lambda *_args: ())
    store = MemoryStateStore()
    executor = SimpleNamespace(drafting=SimpleNamespace(state_store=store))
    fresh = _scenario_draft_request(executor, feature, value.scenario_id)
    assert fresh.authoring_path == draft_artifact_path(value.scenario_id, value.allowed_test_path)
    state_service, *_ = components([], [], {}, store)
    from core.development.scenario_drafting import _initial_state
    state = _initial_state(value)
    store.save(state)
    legacy = _scenario_draft_request(executor, feature, value.scenario_id)
    assert legacy.draft_artifact_path is None
    assert legacy.authoring_path == value.allowed_test_path


def git(root, *args):
    return subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, check=True).stdout.strip()


@pytest.mark.asyncio
async def test_real_git_candidate_freezes_only_new_test_and_preserves_accumulated_test(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    git(root, "init", "-q")
    git(root, "config", "user.name", "Test")
    git(root, "config", "user.email", "test@example.invalid")
    (root / "catalog.py").write_text("class Catalog:\n    pass\n")
    (root / "tests").mkdir()
    previous = "from catalog import Catalog\n\ndef test_previous():\n    assert Catalog\n"
    (root / "tests/test_catalog.py").write_text(previous)
    git(root, "add", ".")
    git(root, "commit", "-qm", "accepted base")
    base = git(root, "rev-parse", "HEAD")
    value = replace(isolated_request(), development_base_revision=base,
        repository_facts=replace(isolated_request().repository_facts, trusted_revision=base))
    target = root / value.authoring_path
    target.parent.mkdir(parents=True)
    target.write_text(candidate("catalog"))
    git(root, "add", "--", value.authoring_path)
    git(root, "commit", "-qm", "isolated draft")
    revision = git(root, "rev-parse", "HEAD")
    service, *_ = components([accepted("catalog-ticket--scenario-draft-1", revision, "draft")],
        [approval("SRC-CATALOG")], {})
    service.source_reader = GitCandidateScenarioSourceReader(root)
    result = await service.draft(value, binding(base))
    assert result.approved
    frozen = result.state.approved_microcycle
    artifact = PythonPytestAdapter().materialise_final_test(
        FinalTestMaterialisationRequest(frozen.model, frozen.fragments, base))
    materialiser = GitFrontierMaterialiser()
    merged = materialiser.materialise(FrontierCandidateRequest(artifact, root, value.allowed_test_path))
    try:
        source = (merged.project_root / value.allowed_test_path).read_text()
        assert "def test_previous():" in source
        assert "def test_catalog_records_item():" in source
        assert not (merged.project_root / value.authoring_path).exists()
        assert git(root, "show", f"{base}:tests/test_catalog.py") == previous.strip()
    finally:
        materialiser.cleanup(merged)

@pytest.mark.asyncio
async def test_canonical_test_write_is_not_admitted_as_draft_candidate():
    from core.execution.work_unit_gateway import ExecutionPolicyEvidence
    value = isolated_request()
    execution = replace(accepted("catalog-ticket--scenario-draft-1", "b" * 40, "draft"),
        policy_evidence=ExecutionPolicyEvidence([value.authoring_path], [value.allowed_test_path]))
    service, gateway, reasoning, reader = components([execution], [], {"b" * 40: candidate("catalog")})
    outcome = await service.draft(value, binding())
    assert not outcome.approved
    assert not reasoning.requests
    assert not reader.calls


@pytest.mark.asyncio
async def test_resume_cannot_change_persisted_authoring_path():
    from core.development.scenario_drafting import _initial_state
    legacy = request("catalog")
    store = MemoryStateStore()
    store.save(_initial_state(legacy))
    service, gateway, reasoning, reader = components([], [], {}, store)
    with pytest.raises(ValueError, match="stale scenario draft"):
        await service.draft(isolated_request(), binding())
    assert not gateway.calls
