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


@pytest.mark.parametrize("boundary", ["yes", "final"])
def test_cli_process_death_resumes_durable_gatekeeper_without_repeating_calls(
    tmp_path, monkeypatch, capsys, boundary,
):
    state, evidence = tmp_path / "state", tmp_path / "evidence"
    parent_pid = os.getpid()
    original_reason = Reasoning.reason
    original_save = StrictTddFeatureRepository.save

    def save(self, feature):
        original_save(self, feature)
        if os.getpid() == parent_pid or not feature.reconciliation_progress:
            return
        node = ChecklistItemProgress.from_dict(feature.reconciliation_progress[0])
        if ((boundary == "yes" and node.individual_attempts)
                or (boundary == "final" and feature.final_reconciliation)):
            os._exit(91)

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
    expected_exit = 0
    assert main(args("resume", state, evidence)[:-2], factory) == expected_exit
    capsys.readouterr()
    assert factory.gateways[0].call_count == 0
    reconciliation = [json.loads(request.prompt) for request in log
                      if getattr(request, "purpose", "") == "athba_checklist_test_reconciliation"]
    assert reconciliation == []
    assert not any(getattr(request, "purpose", "") == "athba_specification_checklist_split" for request in log)
    current = features.load("toggle-project")
    assert current is not None
    assert current.completed_behaviors == before.completed_behaviors
    assert current.canonical_development_base == before.canonical_development_base
    assert {path: open(path, "rb").read() for path in files} == files
    assert current.status == "completed"
    assert current.final_reconciliation[0]["answer"] == "YES"
    replay: Any = Factory([], [])
    assert main(args("resume", state, evidence)[:-2], replay) == expected_exit
    capsys.readouterr()
    assert replay.reasoners[0].call_count == replay.gateways[0].call_count == 0
    assert features.load("toggle-project") == current
