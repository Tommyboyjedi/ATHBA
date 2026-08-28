import json
from pathlib import Path

import pytest

from core.development.work_unit import AcceptanceContract, DevelopmentWorkUnit, WorkUnitStatus
from core.execution.rack_ai_cli_gateway import (
    RackAiCliConfig,
    RackAiCliExecutionGateway,
    RackAiCliTransportError,
)
from core.execution.rack_ai_contract import RepositoryBinding


class FakeProcess:
    def __init__(self, stdout: str, stderr: str = "", returncode: int = 0):
        self._stdout = stdout.encode("utf-8")
        self._stderr = stderr.encode("utf-8")
        self.returncode = returncode

    async def communicate(self) -> tuple[bytes, bytes]:
        return self._stdout, self._stderr


def sample_unit(*, status: WorkUnitStatus = WorkUnitStatus.READY) -> DevelopmentWorkUnit:
    return DevelopmentWorkUnit(
        id="wu-1",
        project_id="p1",
        parent_ticket_id="ticket-1",
        objective="Implement one bounded behavior.",
        allowed_paths=["src/app.py"],
        acceptance=AcceptanceContract(commands=[["pytest", "tests/test_app.py::test_one"]]),
        status=status,
    )


def sample_binding() -> RepositoryBinding:
    return RepositoryBinding(repository_id="repo-1", base_ref="main", base_sha="a" * 40)


@pytest.mark.asyncio
async def test_gateway_returns_structured_success_and_uses_argument_array(monkeypatch):
    captured: dict[str, object] = {}

    async def fake_exec(*args, **kwargs):
        captured["args"] = args
        captured["kwargs"] = kwargs
        spec_path = Path(args[7])
        captured["spec_path"] = spec_path
        captured["payload"] = json.loads(spec_path.read_text(encoding="utf-8"))
        return FakeProcess(
            json.dumps(
                {
                    "workload_id": "p1",
                    "work_unit_id": "wu-1",
                    "change_id": "p1--wu-1",
                    "selected_worker_id": "local-coder",
                    "placement": {"worker_ids": ["local-coder"], "resource_ids": ["gpu-2060"]},
                    "status": "checks_passed",
                    "acceptance_verdict": "approved",
                    "branch": "rack/change/p1--wu-1",
                    "worktree_path": "/srv/rack-ai/worktrees/p1--wu-1",
                    "packet_path": "/srv/rack-ai/state/p1--wu-1.json",
                }
            )
        )

    monkeypatch.setattr("core.execution.rack_ai_cli_gateway.asyncio.create_subprocess_exec", fake_exec)

    gateway = RackAiCliExecutionGateway(
        "p1",
        sample_binding(),
        RackAiCliConfig(executable="cargo", rack_ai_root="/srv/rack-ai", state_root="/srv/rack-ai"),
    )
    result = await gateway.execute(sample_unit())

    assert result.accepted is True
    assert result.selected_worker_id == "local-coder"
    assert result.placement == {"worker_ids": ["local-coder"], "resource_ids": ["gpu-2060"]}
    assert captured["args"] == (
        "cargo",
        "run",
        "-q",
        "-p",
        "rack_ai_cli",
        "--",
        "work-unit",
        str(captured["spec_path"]),
        "--repo-root",
        "/srv/rack-ai",
        "--state-root",
        "/srv/rack-ai",
        "--emit-json",
    )
    assert captured["kwargs"]["cwd"] == "/srv/rack-ai"
    assert captured["payload"]["version"] == "rack-ai/work-unit/v1"
    assert captured["payload"]["work_unit"]["readiness"] == {"ready": True, "depends_on": []}
    assert not Path(captured["spec_path"]).exists()


@pytest.mark.asyncio
async def test_gateway_returns_structured_rejection_even_on_nonzero_exit(monkeypatch):
    async def fake_exec(*_args, **_kwargs):
        return FakeProcess(
            json.dumps(
                {
                    "work_unit_id": "wu-1",
                    "change_id": "p1--wu-1",
                    "status": "checks_failed",
                    "acceptance_verdict": "rejected",
                    "last_error": "acceptance command failed",
                }
            ),
            returncode=1,
        )

    monkeypatch.setattr("core.execution.rack_ai_cli_gateway.asyncio.create_subprocess_exec", fake_exec)

    gateway = RackAiCliExecutionGateway("p1", sample_binding())
    result = await gateway.execute(sample_unit())

    assert result.accepted is False
    assert result.status == "checks_failed"
    assert result.error == "acceptance command failed"


@pytest.mark.asyncio
async def test_gateway_preserves_structured_failed_status(monkeypatch):
    async def fake_exec(*_args, **_kwargs):
        return FakeProcess(
            json.dumps(
                {
                    "work_unit_id": "wu-1",
                    "change_id": "p1--wu-1",
                    "status": "failed",
                    "acceptance_verdict": "rejected",
                }
            ),
            returncode=1,
        )

    monkeypatch.setattr("core.execution.rack_ai_cli_gateway.asyncio.create_subprocess_exec", fake_exec)

    gateway = RackAiCliExecutionGateway("p1", sample_binding())
    result = await gateway.execute(sample_unit())

    assert result.accepted is False
    assert result.status == "failed"


@pytest.mark.asyncio
async def test_gateway_raises_on_nonzero_exit_without_usable_json(monkeypatch):
    async def fake_exec(*_args, **_kwargs):
        return FakeProcess("", stderr="cargo failed", returncode=1)

    monkeypatch.setattr("core.execution.rack_ai_cli_gateway.asyncio.create_subprocess_exec", fake_exec)

    gateway = RackAiCliExecutionGateway("p1", sample_binding())
    with pytest.raises(RackAiCliTransportError, match="cargo failed"):
        await gateway.execute(sample_unit())


@pytest.mark.asyncio
async def test_gateway_raises_on_empty_stdout(monkeypatch):
    async def fake_exec(*_args, **_kwargs):
        return FakeProcess("", stderr="no payload")

    monkeypatch.setattr("core.execution.rack_ai_cli_gateway.asyncio.create_subprocess_exec", fake_exec)

    gateway = RackAiCliExecutionGateway("p1", sample_binding())
    with pytest.raises(RackAiCliTransportError, match="returned no JSON"):
        await gateway.execute(sample_unit())


@pytest.mark.asyncio
async def test_gateway_raises_on_malformed_json(monkeypatch):
    async def fake_exec(*_args, **_kwargs):
        return FakeProcess("{not-json}", stderr="bad json")

    monkeypatch.setattr("core.execution.rack_ai_cli_gateway.asyncio.create_subprocess_exec", fake_exec)

    gateway = RackAiCliExecutionGateway("p1", sample_binding())
    with pytest.raises(RackAiCliTransportError, match="untrustworthy output"):
        await gateway.execute(sample_unit())


@pytest.mark.asyncio
async def test_gateway_raises_on_missing_required_identifiers(monkeypatch):
    async def fake_exec(*_args, **_kwargs):
        return FakeProcess(
            json.dumps(
                {
                    "status": "checks_passed",
                    "acceptance_verdict": "approved",
                }
            ),
            stderr="missing ids",
        )

    monkeypatch.setattr("core.execution.rack_ai_cli_gateway.asyncio.create_subprocess_exec", fake_exec)

    gateway = RackAiCliExecutionGateway("p1", sample_binding())
    with pytest.raises(RackAiCliTransportError, match="missing required field: work_unit_id"):
        await gateway.execute(sample_unit())


@pytest.mark.asyncio
async def test_gateway_rejects_non_ready_units_before_subprocess(monkeypatch):
    called = False

    async def fake_exec(*_args, **_kwargs):
        nonlocal called
        called = True
        return FakeProcess("{}")

    monkeypatch.setattr("core.execution.rack_ai_cli_gateway.asyncio.create_subprocess_exec", fake_exec)

    gateway = RackAiCliExecutionGateway("p1", sample_binding())
    with pytest.raises(ValueError, match="marked ready for execution"):
        await gateway.execute(sample_unit(status=WorkUnitStatus.PLANNED))
    assert called is False
