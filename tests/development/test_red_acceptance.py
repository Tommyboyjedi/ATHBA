import asyncio
import json
import subprocess
import sys
from pathlib import Path

from core.development.red_acceptance import (
    PROBE_MARKER,
    PytestProbePacketLoader,
    RedAcceptanceDependencies,
    RedAcceptanceRequest,
    RedAcceptanceService,
    RedBehaviorVerifier,
)
from core.development.tdd_progression import BehaviorContract, BehaviorContractRequirement, SourceRequirementClause, TddStepProposal

TEMPLATE_PATH = Path(__file__).resolve().parents[2] / "scripts" / "assert_test_fails_template.py"


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
    root.mkdir(parents=True)
    (root / Path(production_path).parent).mkdir(parents=True, exist_ok=True)
    (root / Path(test_path).parent).mkdir(parents=True, exist_ok=True)
    (root / production_path).write_text(production_source, encoding="utf-8")
    (root / test_path).write_text(test_source, encoding="utf-8")
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    subprocess.run(["git", "add", "."], cwd=root, check=True)
    subprocess.run(["git", "-c", "user.name=ATHBA", "-c", "user.email=athba@example.test", "commit", "-qm", "seed"], cwd=root, check=True)
    return root, _git(["rev-parse", "HEAD"], root)


def _install_probe_script(root: Path) -> None:
    script_path = root / "scripts" / "assert_test_fails.py"
    script_path.parent.mkdir(exist_ok=True)
    script_path.write_text(TEMPLATE_PATH.read_text(encoding="utf-8"), encoding="utf-8")


def _synthetic_packet(path: Path, **overrides: object) -> str:
    probe = {
        "pytest_runtime_available": True,
        "collection_succeeded": True,
        "requested_node_found": True,
        "requested_node_executed": True,
        "outcome": "failed",
        "reported_node_id": "tests/test_target.py::test_behavior",
        "collected_node_ids": ["tests/test_target.py::test_behavior"],
        "setup_outcome": "passed",
        "call_outcome": "failed",
        "teardown_outcome": "passed",
        "was_xfail": False,
        "was_xpass": False,
        "failure_phase": "call",
        "exception_type": "AssertionError",
        "failure_message": "assert 1 == 2",
        "traceback_location": "tests/test_target.py:7",
        "stdout": "",
        "stderr": "",
        "evidence_refs": [str(path)],
    }
    probe.update(overrides)
    path.write_text(json.dumps({"commands": [{"stdout": f"{PROBE_MARKER} {json.dumps(probe)}"}]}), encoding="utf-8")
    return str(path)


def _live_packet(root: Path, test_node: str, packet_name: str = "probe-packet.json") -> tuple[str, subprocess.CompletedProcess[str]]:
    _install_probe_script(root)
    result = subprocess.run([sys.executable, "-B", "scripts/assert_test_fails.py", test_node], cwd=root, check=True, capture_output=True, text=True)
    packet_path = root / packet_name
    packet_path.write_text(json.dumps({"commands": [{"stdout": result.stdout, "stderr": result.stderr}]}), encoding="utf-8")
    return str(packet_path), result


def _live_probe(root: Path, test_node: str, packet_name: str = "probe-packet.json"):
    packet, result = _live_packet(root, test_node, packet_name)
    return PytestProbePacketLoader().load(packet), result, packet


def _evaluate(request: RedAcceptanceRequest):
    service = RedAcceptanceService(RedAcceptanceDependencies(verifier=RedBehaviorVerifier()))
    return asyncio.run(service.evaluate(request))


def test_structured_probe_reports_exact_collection_and_node_execution(tmp_path: Path):
    test_path = "tests/test_task_queue.py"
    production_path = "task_queue.py"
    root, _ = _repo(
        tmp_path,
        production_path,
        "class TaskQueue:\n    def add(self, task_id: str) -> None:\n        pass\n",
        test_path,
        "from task_queue import TaskQueue\n\n\ndef test_add_persists_task():\n    queue = TaskQueue()\n    queue.add('t1')\n    assert queue.size() == 1\n",
    )

    probe, result, _ = _live_probe(root, f"{test_path}::test_add_persists_task")

    assert result.returncode == 0
    assert probe.collection_succeeded is True
    assert probe.requested_node_found is True
    assert probe.requested_node_executed is True
    assert probe.reported_node_id == f"{test_path}::test_add_persists_task"
    assert probe.collected_node_ids == [f"{test_path}::test_add_persists_task"]
    assert probe.setup_outcome == "passed"
    assert probe.call_outcome == "failed"
    assert probe.teardown_outcome == "passed"
    assert probe.outcome == "failed"


def test_structured_probe_does_not_infer_execution_from_helper_return_code(tmp_path: Path):
    test_path = "tests/test_counter.py"
    production_path = "counter.py"
    root, _ = _repo(
        tmp_path,
        production_path,
        "class Counter:\n    pass\n",
        test_path,
        "import missing_dependency\n\n\ndef test_increment_changes_total():\n    assert False\n",
    )

    probe, result, _ = _live_probe(root, f"{test_path}::test_increment_changes_total")

    assert result.returncode == 0
    assert probe.collection_succeeded is False
    assert probe.requested_node_found is False
    assert probe.requested_node_executed is False
    assert probe.failure_phase == "collection"
    assert probe.outcome == "error"


def test_structured_probe_detects_skip(tmp_path: Path):
    test_path = "tests/test_counter.py"
    production_path = "counter.py"
    root, _ = _repo(
        tmp_path,
        production_path,
        "class Counter:\n    pass\n",
        test_path,
        "import pytest\n\n\ndef test_increment_increases_value():\n    pytest.skip('skip from runtime hook')\n",
    )

    probe, _, _ = _live_probe(root, f"{test_path}::test_increment_increases_value")

    assert probe.requested_node_executed is True
    assert probe.call_outcome == "skipped"
    assert probe.outcome == "skipped"


def test_structured_probe_detects_xfail_and_xpass(tmp_path: Path):
    test_path = "tests/test_marks.py"
    production_path = "marks.py"
    root, _ = _repo(
        tmp_path,
        production_path,
        "def identity(value: int) -> int:\n    return value\n",
        test_path,
        "import pytest\n\n\n@pytest.mark.xfail(reason='expected red')\ndef test_expected_failure():\n    assert False\n\n\n@pytest.mark.xfail(strict=False, reason='unexpected pass')\ndef test_unexpected_pass():\n    assert True\n",
    )

    xfail_probe, _, _ = _live_probe(root, f"{test_path}::test_expected_failure", "xfail-packet.json")
    xpass_probe, _, _ = _live_probe(root, f"{test_path}::test_unexpected_pass", "xpass-packet.json")

    assert xfail_probe.was_xfail is True
    assert xfail_probe.outcome == "xfailed"
    assert xpass_probe.was_xpass is True
    assert xpass_probe.outcome == "xpassed"


def test_structured_probe_distinguishes_setup_error_from_call_failure(tmp_path: Path):
    test_path = "tests/test_counter.py"
    production_path = "counter.py"
    setup_root, _ = _repo(
        tmp_path / "setup-case",
        production_path,
        "class Counter:\n    pass\n",
        test_path,
        "import pytest\n\n\n@pytest.fixture\ndef broken_fixture():\n    raise RuntimeError('fixture broke')\n\n\ndef test_increment_uses_fixture(broken_fixture):\n    assert True\n",
    )
    call_root, _ = _repo(
        tmp_path / "call-case",
        production_path,
        "class Counter:\n    def increment(self) -> None:\n        pass\n",
        test_path,
        "from counter import Counter\n\n\ndef test_increment_changes_total():\n    counter = Counter()\n    counter.increment()\n    assert counter.total() == 1\n",
    )

    setup_probe, _, _ = _live_probe(setup_root, f"{test_path}::test_increment_uses_fixture", "setup-packet.json")
    call_probe, _, _ = _live_probe(call_root, f"{test_path}::test_increment_changes_total", "call-packet.json")

    assert setup_probe.setup_outcome == "failed"
    assert setup_probe.call_outcome == "not_run"
    assert setup_probe.failure_phase == "setup"
    assert call_probe.setup_outcome == "passed"
    assert call_probe.call_outcome == "failed"
    assert call_probe.failure_phase == "call"


def test_call_phase_assertion_failure_can_be_valid_red(tmp_path: Path):
    test_path = "tests/test_task_queue.py"
    production_path = "task_queue.py"
    root, revision = _repo(
        tmp_path,
        production_path,
        "class TaskQueue:\n    def add(self, task_id: str) -> None:\n        pass\n",
        test_path,
        "from task_queue import TaskQueue\n\n\ndef test_add_persists_task():\n    queue = TaskQueue()\n    queue.add('t1')\n    assert queue.size() == 1\n",
    )
    _, _, packet = _live_probe(root, f"{test_path}::test_add_persists_task")
    request = RedAcceptanceRequest(
        contract=_contract("TaskQueue", production_path, test_path),
        step=_step(test_path, production_path, f"{test_path}::test_add_persists_task", "Adding a task persists it."),
        repository_root=str(root),
        candidate_revision=revision,
        trusted_base_revision="a" * 40,
        candidate_change_id="change-step-1",
        evidence_location=packet,
    )

    result = _evaluate(request)

    assert result.is_valid_red is True
    assert result.analysis.artifact_assessment.disposition == "valid_executable_test"
    assert result.analysis.verifier_result.disposition == "valid_red"


def test_console_text_remains_evidence_only_for_classification(tmp_path: Path):
    test_path = "tests/test_messages.py"
    production_path = "messages.py"
    root, revision = _repo(
        tmp_path,
        production_path,
        "class MessageEmitter:\n    def send(self) -> None:\n        pass\n",
        test_path,
        "import sys\nfrom messages import MessageEmitter\n\n\ndef test_send_emits_signal():\n    emitter = MessageEmitter()\n    print('ERROR collecting 1 selected xfailed skipped')\n    sys.stderr.write('xpassed skipped\\n')\n    emitter.send()\n    assert emitter.sent_count() == 1\n",
    )
    _, _, packet = _live_probe(root, f"{test_path}::test_send_emits_signal")
    request = RedAcceptanceRequest(
        contract=_contract("MessageEmitter", production_path, test_path),
        step=_step(test_path, production_path, f"{test_path}::test_send_emits_signal", "Sending emits a signal."),
        repository_root=str(root),
        candidate_revision=revision,
        trusted_base_revision="b" * 40,
        candidate_change_id="change-step-1",
        evidence_location=packet,
    )

    result = _evaluate(request)
    probe = result.analysis.artifact_assessment.pytest_probe

    assert probe.collection_succeeded is True
    assert probe.requested_node_executed is True
    assert probe.outcome == "failed"
    assert "ERROR collecting" in (probe.stdout or "")
    assert "xpassed skipped" in (probe.stdout or "")
    assert result.analysis.artifact_assessment.disposition == "valid_executable_test"
    assert result.is_valid_red is True


def test_syntax_error_is_not_red(tmp_path: Path):
    test_path = "tests/test_thermostat.py"
    production_path = "thermostat.py"
    root, revision = _repo(
        tmp_path,
        production_path,
        "class Thermostat:\n    pass\n",
        test_path,
        "def test_set_target_temperature(:\n    pass\n",
    )
    request = RedAcceptanceRequest(
        contract=_contract("Thermostat", production_path, test_path),
        step=_step(test_path, production_path, f"{test_path}::test_set_target_temperature", "Setting a temperature updates the target."),
        repository_root=str(root),
        candidate_revision=revision,
        trusted_base_revision="a" * 40,
        candidate_change_id="change-step-1",
        evidence_location=_synthetic_packet(tmp_path / "thermostat-packet.json", outcome="error", requested_node_found=False, requested_node_executed=False),
    )

    result = _evaluate(request)

    assert result.is_valid_red is False
    assert result.analysis.artifact_assessment.disposition == "syntax_invalid"
    assert result.analysis.verifier_result.disposition == "invalid_test"


def test_passing_test_remains_wrong_behavior(tmp_path: Path):
    test_path = "tests/test_led_panel.py"
    production_path = "led_panel.py"
    root, revision = _repo(
        tmp_path,
        production_path,
        "class LedPanel:\n    def turn_on(self) -> None:\n        pass\n",
        test_path,
        "from led_panel import LedPanel\n\n\ndef test_brightness_changes_level():\n    panel = LedPanel()\n    panel.turn_on()\n    assert True\n",
    )
    _, _, packet = _live_probe(root, f"{test_path}::test_brightness_changes_level")
    request = RedAcceptanceRequest(
        contract=_contract("LedPanel", production_path, test_path),
        step=_step(test_path, production_path, f"{test_path}::test_brightness_changes_level", "Changing brightness updates the displayed level."),
        repository_root=str(root),
        candidate_revision=revision,
        trusted_base_revision="a" * 40,
        candidate_change_id="change-step-1",
        evidence_location=packet,
    )

    result = _evaluate(request)

    assert result.is_valid_red is False
    assert result.analysis.artifact_assessment.disposition == "valid_executable_test"
    assert result.analysis.verifier_result.disposition == "wrong_behavior"
