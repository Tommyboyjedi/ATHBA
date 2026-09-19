"""Complete fake TDD once; only final specification routing changes acceptance."""
import json
from typing import Any

import pytest

from core.development.strict_tdd_feature_store import StrictTddFeatureRepository
from core.execution.reasoning_gateway import ReasoningResult
from scripts.run_pr23_strict_tdd_feature import main
from tests.development import test_pr23_strict_tdd_runner as fixture
from tests.development.test_pr23_strict_tdd_runner import prevent_live_boundaries


@pytest.mark.parametrize("unsupported", [False, True])
def test_mixed_final_routing_preserves_completed_work_and_original_checklist(tmp_path, monkeypatch, capsys, unsupported):
    source = fixture.REQUIREMENT + " Deletion is not required. Component must be dependency-free. Keep the component small, direct and readable."
    if unsupported:
        source += " Make the component beautiful."
    monkeypatch.setattr(fixture, "REQUIREMENT", source)
    original = fixture.Reasoning.reason
    state, evidence = tmp_path / "state", tmp_path / "evidence"
    repository = state / "projects/toggle-project/repository"
    features = StrictTddFeatureRepository(state / "features")
    before: dict[str, Any] = {}
    log: list[Any] = []
    counts: list[Any] = []

    def frozen_files():
        return {str(path.relative_to(state)): path.read_bytes()
                for folder in ("microcycles", "scenario-drafts", "revisions")
                for path in (state / folder).rglob("*.json")}

    async def reason(self, request):
        if request.purpose == "athba_specification_checklist":
            response = await original(self, request)
            payload = json.loads(response.text)
            payload["items"][0].update(source_quote="It can be instantiated, begins in the off state, and calling toggle changes it to the on state.", subject="toggle")
            obligations = [
                ("Deletion is not required.", "non_goal", "Deletion", "constraint"),
                ("Component must be dependency-free.", "required", "dependency-free", "quality"),
            ]
            obligations.extend(("Keep the component small, direct and readable.", "required", quality, "quality")
                               for quality in ("small", "direct", "readable"))
            if unsupported:
                obligations.append(("Make the component beautiful.", "required", "beautiful", "quality"))
            for index, (text, modality, subject, kind) in enumerate(obligations, start=2):
                payload["items"].append(dict(ref=f"CHK-{index}", text=text, source_quote=text,
                                             modality=modality, subject=subject, kind=kind))
            return ReasoningResult(json.dumps(payload))
        if request.purpose == "athba_checklist_test_reconciliation":
            assert json.loads(request.prompt)["checklist_item"]["ref"] == "CHK-1"
            before.update(feature=features.load("toggle-project"), files=frozen_files(),
                          sha=fixture.git(repository, "rev-parse", "refs/heads/main"))
        return await original(self, request)

    monkeypatch.setattr(fixture.Reasoning, "reason", reason)
    factory: Any = fixture.Factory(log, counts)
    code = 2 if unsupported else 0
    assert main(fixture.args("start", state, evidence)[:-2], factory) == code
    capsys.readouterr()
    current = features.load("toggle-project")
    assert current is not None
    assert current.completed_behaviors == before["feature"].completed_behaviors
    assert current.gatekeeper_payload == before["feature"].gatekeeper_payload
    assert current.gatekeeper_payload["checklist"]["requirement_text"] == source
    assert current.canonical_development_base == before["sha"]
    assert frozen_files() == before["files"]
    results = current.final_reconciliation
    assert [record["answer"] for record in results] == ["YES", "NOT_APPLICABLE", "YES"] + ["NOT_APPLICABLE"] * 3 + (["NO"] if unsupported else [])
    assert results[1]["evidence_policy"] == "non_goal_scope"
    assert results[2]["evidence_policy"] == "dependency_free"
    assert all(record["accepted_test_names"] == [] for record in results[1:])
    assert all(record["evidence_status"] == "covered_by_engineering_policy" for record in results[3:6])
    if unsupported:
        assert current.blocked_reason == "specification_gatekeeper_failed"
        assert results[-1]["evidence_status"] == "unsupported_evidence_policy"
    replay: Any = fixture.Factory(log, counts)
    assert main(fixture.args("resume", state, evidence)[:-2], replay) == code
    capsys.readouterr()
    assert replay.reasoners[0].call_count == replay.gateways[0].call_count == 0
    assert frozen_files() == before["files"]
    assert fixture.git(repository, "rev-parse", "refs/heads/main") == before["sha"]
