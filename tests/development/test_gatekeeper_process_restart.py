"""Actual process death at atomic feature saves, with fake reasoning/execution only."""
import json
import multiprocessing
import os
from typing import Any

import pytest

from core.development.reconciliation_progress import ChecklistItemProgress
from core.development.strict_tdd_feature_store import StrictTddFeatureRepository
from core.development.strict_tdd_run_store import StrictTddRunStateRepository
from core.execution.reasoning_gateway import ReasoningResult
from scripts.run_pr23_strict_tdd_feature import main
from tests.development.test_pr23_strict_tdd_runner import (
    Factory, Reasoning, args, prevent_live_boundaries,
)


@pytest.mark.parametrize("boundary", ["yes", "split", "rejected_split", "final"])
def test_cli_process_death_resumes_durable_gatekeeper_without_repeating_calls(
    tmp_path, monkeypatch, capsys, boundary,
):
    state, evidence = tmp_path / "state", tmp_path / "evidence"
    parent_pid = os.getpid()
    original_reason = Reasoning.reason
    original_save = StrictTddFeatureRepository.save

    async def reason(self, request):
        if request.purpose == "athba_checklist_test_reconciliation":
            prompt = json.loads(request.prompt)
            if boundary not in {"yes", "final"} and prompt["checklist_item"]["ref"] == "CHK-1":
                self.call_count += 1
                self.log.append(request)
                return ReasoningResult(json.dumps({"answer": "NO", "selected_test_names": [],
                                                   "rationale": "Atomic tests do not cover compound item"}))
        if request.purpose == "athba_specification_checklist_split":
            self.call_count += 1
            self.log.append(request)
            prompt = json.loads(request.prompt)
            item = prompt["parent"]
            texts = ["A ToggleSwitch begins off.", "A ToggleSwitch can toggle on."]
            if boundary == "rejected_split":
                texts[1] = texts[0]
            return ReasoningResult(json.dumps({"disposition": "split", "rationale": "Separate obligations",
                "children": [{**item, "text": text} for text in texts]}))
        return await original_reason(self, request)

    def save(self, feature):
        original_save(self, feature)
        if os.getpid() == parent_pid or not feature.reconciliation_progress:
            return
        node = ChecklistItemProgress.from_dict(feature.reconciliation_progress[0])
        if ((boundary == "yes" and node.individual_attempts)
                or (boundary in {"split", "rejected_split"} and node.split is not None)
                or (boundary == "final" and feature.final_reconciliation)):
            os._exit(91)

    monkeypatch.setattr(Reasoning, "reason", reason)
    monkeypatch.setattr(StrictTddFeatureRepository, "save", save)

    def start():
        factory: Any = Factory([], [])
        main(args("start", state, evidence)[:-2], factory)

    process = multiprocessing.get_context("fork").Process(target=start)
    process.start()
    process.join(120)
    if process.is_alive():
        process.terminate()
        process.join(10)
        pytest.fail("fake-only process restart fixture exceeded its bound")
    assert process.exitcode == 91
    run_before = StrictTddRunStateRepository(state / "runs").load("toggle-run")
    assert run_before is not None and run_before.transition_in_flight is not None
    features = StrictTddFeatureRepository(state / "features")
    before = features.load("toggle-project")
    assert before is not None
    files = {str(path): path.read_bytes() for folder in ("microcycles", "scenario-drafts", "revisions")
             for path in (state / folder).rglob("*.json")}
    log: list[Any] = []
    factory: Any = Factory(log, [])
    expected_exit = 2 if boundary == "rejected_split" else 0
    assert main(args("resume", state, evidence)[:-2], factory) == expected_exit
    capsys.readouterr()
    assert factory.gateways[0].call_count == 0
    reconciliation = [json.loads(request.prompt) for request in log
                      if getattr(request, "purpose", "") == "athba_checklist_test_reconciliation"]
    assert [prompt["checklist_item"]["ref"] for prompt in reconciliation] == (
        ["CHK-1-S001", "CHK-1-S002"] if boundary == "split" else [])
    assert not any(getattr(request, "purpose", "") == "athba_specification_checklist_split" for request in log)
    current = features.load("toggle-project")
    assert current is not None
    assert current.completed_behaviors == before.completed_behaviors
    assert current.canonical_development_base == before.canonical_development_base
    assert {path: open(path, "rb").read() for path in files} == files
    assert current.status == ("blocked" if boundary == "rejected_split" else "completed")
    assert current.final_reconciliation[0]["answer"] == ("YES" if boundary in {"yes", "final"} else "NO")
    if boundary == "rejected_split":
        assert current.final_reconciliation[0]["blocked_reason"] == "specification_gatekeeper_unsplittable"
    replay: Any = Factory([], [])
    assert main(args("resume", state, evidence)[:-2], replay) == expected_exit
    capsys.readouterr()
    assert replay.reasoners[0].call_count == replay.gateways[0].call_count == 0
    assert features.load("toggle-project") == current
