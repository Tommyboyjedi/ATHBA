import json
import subprocess
from pathlib import Path

from core.development.red_acceptance import PROBE_MARKER, RedAcceptanceDependencies, RedAcceptanceRequest, RedAcceptanceService, RedBehaviorVerifier
from core.development.tdd_progression import BehaviorContract, BehaviorContractRequirement, SourceRequirementClause, TddStepProposal


def _contract(component_name: str, production_path: str, test_path: str) -> BehaviorContract:
    return BehaviorContract(
        id=f"contract-{component_name.lower()}",
        project_id=f"project-{component_name.lower()}",
        component_name=component_name,
        capability=f"Manage {component_name} behavior.",
        requirement_source=f"Build {component_name}.",
        source_clauses=[SourceRequirementClause(ref="SRC-1", text=f"{component_name} supports one observable behavior.", kind="behavior")],
        observable_requirements=[
            BehaviorContractRequirement(
                ref="REQ-1",
                source_refs=["SRC-1"],
                summary="Provide one behavior.",
                observable_outcome="The target operation changes externally visible state.",
                test_hint="test_behavior",
                error_expectation="Invalid requests raise ValueError.",
                preserves_state_on_failure=True,
            )
        ],
        invariants=["state remains consistent"],
        production_paths=[production_path],
        test_paths=[test_path],
        public_api=["placeholder()"],
        error_semantics=["invalid requests raise ValueError"],
    )


def _step(test_path: str, production_path: str, test_name: str, behavior: str) -> TddStepProposal:
    return TddStepProposal(
        step_id="step-1",
        requirement_refs=["REQ-1"],
        focused_behavior=behavior,
        test_name=test_name,
        expected_result="The observable state changes as requested.",
        test_path=test_path,
        production_path=production_path,
        red_objective="Add one failing test.",
        green_objective="Implement only enough code.",
        reason_next_smallest="Smallest observable slice.",
    )


def _git(args: list[str], cwd: Path) -> str:
    result = subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True)
    return result.stdout.strip()


def _repo(tmp_path: Path, production_path: str, production_source: str, test_path: str, test_source: str) -> tuple[Path, str]:
    root = tmp_path / "target"
    root.mkdir()
    (root / Path(production_path).parent).mkdir(parents=True, exist_ok=True)
    (root / Path(test_path).parent).mkdir(parents=True, exist_ok=True)
    (root / production_path).write_text(production_source, encoding="utf-8")
    (root / test_path).write_text(test_source, encoding="utf-8")
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    subprocess.run(["git", "add", "."], cwd=root, check=True)
    subprocess.run(["git", "-c", "user.name=ATHBA", "-c", "user.email=athba@example.test", "commit", "-qm", "seed"], cwd=root, check=True)
    return root, _git(["rev-parse", "HEAD"], root)


def _packet(path: Path, *, outcome: str = "failed", collection_succeeded: bool = True, requested_node_found: bool = True, requested_node_executed: bool = True, failure_phase: str | None = "call", exception_type: str | None = "AssertionError", failure_message: str | None = "assert 1 == 2") -> str:
    probe = {
        "pytest_runtime_available": True,
        "collection_succeeded": collection_succeeded,
        "requested_node_found": requested_node_found,
        "requested_node_executed": requested_node_executed,
        "outcome": outcome,
        "failure_phase": failure_phase,
        "exception_type": exception_type,
        "failure_message": failure_message,
        "traceback_location": "tests/test_target.py:7",
        "stdout": "",
        "stderr": "",
        "evidence_refs": [str(path)],
    }
    path.write_text(json.dumps({"commands": [{"stdout": f"{PROBE_MARKER} {json.dumps(probe)}"}]}), encoding="utf-8")
    return str(path)


def test_task_queue_valid_red_is_accepted_for_semantic_analysis(tmp_path: Path):
    test_path = "tests/test_task_queue.py"
    production_path = "task_queue.py"
    repo_root, revision = _repo(
        tmp_path,
        production_path,
        "class TaskQueue:\n    def add(self, task_id: str) -> None:\n        pass\n",
        test_path,
        "from task_queue import TaskQueue\n\n\ndef test_add_persists_task():\n    queue = TaskQueue()\n    queue.add('t1')\n    assert queue.size() == 1\n",
    )
    request = RedAcceptanceRequest(
        contract=_contract("TaskQueue", production_path, test_path),
        step=_step(test_path, production_path, f"{test_path}::test_add_persists_task", "Adding a task persists it."),
        repository_root=str(repo_root),
        candidate_revision=revision,
        trusted_base_revision="a" * 40,
        candidate_change_id="change-step-1",
        evidence_location=_packet(tmp_path / "task-queue-packet.json"),
    )

    result = __import__("asyncio").run(RedAcceptanceService(RedAcceptanceDependencies(verifier=RedBehaviorVerifier())).evaluate(request))

    assert result.is_valid_red is True
    assert result.analysis.artifact_assessment.disposition == "valid_executable_test"
    assert result.analysis.behavior_evidence.target_operation_candidates == ["TaskQueue", "queue.add", "queue.size"]


def test_thermostat_syntax_error_is_not_red(tmp_path: Path):
    test_path = "tests/test_thermostat.py"
    production_path = "thermostat.py"
    repo_root, revision = _repo(
        tmp_path,
        production_path,
        "class Thermostat:\n    pass\n",
        test_path,
        "def test_set_target_temperature(:\n    pass\n",
    )
    request = RedAcceptanceRequest(
        contract=_contract("Thermostat", production_path, test_path),
        step=_step(test_path, production_path, f"{test_path}::test_set_target_temperature", "Setting a temperature updates the target."),
        repository_root=str(repo_root),
        candidate_revision=revision,
        trusted_base_revision="a" * 40,
        candidate_change_id="change-step-1",
        evidence_location=_packet(tmp_path / "thermostat-packet.json", outcome="error", requested_node_found=False, requested_node_executed=False),
    )

    result = __import__("asyncio").run(RedAcceptanceService(RedAcceptanceDependencies(verifier=RedBehaviorVerifier())).evaluate(request))

    assert result.is_valid_red is False
    assert result.analysis.artifact_assessment.disposition == "syntax_invalid"
    assert result.analysis.verifier_result.disposition == "invalid_test"


def test_collection_failure_is_not_red(tmp_path: Path):
    test_path = "tests/test_inventory_counter.py"
    production_path = "inventory_counter.py"
    repo_root, revision = _repo(
        tmp_path,
        production_path,
        "class InventoryCounter:\n    pass\n",
        test_path,
        "from inventory_counter import InventoryCounter\n\n\ndef test_increment_changes_total():\n    counter = InventoryCounter()\n    assert counter.total() == 1\n",
    )
    request = RedAcceptanceRequest(
        contract=_contract("InventoryCounter", production_path, test_path),
        step=_step(test_path, production_path, f"{test_path}::test_increment_changes_total", "Incrementing increases the total."),
        repository_root=str(repo_root),
        candidate_revision=revision,
        trusted_base_revision="a" * 40,
        candidate_change_id="change-step-1",
        evidence_location=_packet(tmp_path / "inventory-packet.json", outcome="error", collection_succeeded=False, requested_node_executed=False, failure_phase="setup", exception_type="ImportError", failure_message="ImportError while collecting tests"),
    )

    result = __import__("asyncio").run(RedAcceptanceService(RedAcceptanceDependencies(verifier=RedBehaviorVerifier())).evaluate(request))

    assert result.is_valid_red is False
    assert result.analysis.artifact_assessment.disposition == "bootstrap_or_fixture_failure"
    assert result.analysis.verifier_result.disposition == "invalid_test"


def test_skipped_test_is_not_red(tmp_path: Path):
    test_path = "tests/test_counter.py"
    production_path = "counter.py"
    repo_root, revision = _repo(
        tmp_path,
        production_path,
        "class Counter:\n    pass\n",
        test_path,
        "import pytest\n\n\n@pytest.mark.skip\ndef test_increment_increases_value():\n    assert False\n",
    )
    request = RedAcceptanceRequest(
        contract=_contract("Counter", production_path, test_path),
        step=_step(test_path, production_path, f"{test_path}::test_increment_increases_value", "Incrementing increases value."),
        repository_root=str(repo_root),
        candidate_revision=revision,
        trusted_base_revision="a" * 40,
        candidate_change_id="change-step-1",
        evidence_location=_packet(tmp_path / "counter-packet.json", outcome="skipped", requested_node_executed=False),
    )

    result = __import__("asyncio").run(RedAcceptanceService(RedAcceptanceDependencies(verifier=RedBehaviorVerifier())).evaluate(request))

    assert result.analysis.artifact_assessment.disposition == "skipped"
    assert result.analysis.verifier_result.disposition == "invalid_test"


def test_wrong_behavior_is_distinguished_from_valid_red(tmp_path: Path):
    test_path = "tests/test_led_panel.py"
    production_path = "led_panel.py"
    repo_root, revision = _repo(
        tmp_path,
        production_path,
        "class LedPanel:\n    def turn_on(self) -> None:\n        pass\n",
        test_path,
        "from led_panel import LedPanel\n\n\ndef test_brightness_changes_level():\n    panel = LedPanel()\n    panel.turn_on()\n",
    )
    request = RedAcceptanceRequest(
        contract=_contract("LedPanel", production_path, test_path),
        step=_step(test_path, production_path, f"{test_path}::test_brightness_changes_level", "Changing brightness updates the displayed level."),
        repository_root=str(repo_root),
        candidate_revision=revision,
        trusted_base_revision="a" * 40,
        candidate_change_id="change-step-1",
        evidence_location=_packet(tmp_path / "led-packet.json", outcome="passed", failure_phase=None, exception_type=None, failure_message=None),
    )

    result = __import__("asyncio").run(RedAcceptanceService(RedAcceptanceDependencies(verifier=RedBehaviorVerifier())).evaluate(request))

    assert result.is_valid_red is False
    assert result.analysis.artifact_assessment.disposition == "valid_executable_test"
    assert result.analysis.verifier_result.disposition == "wrong_behavior"
