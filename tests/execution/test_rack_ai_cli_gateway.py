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
        acceptance=AcceptanceContract(commands=[["python3", "-m", "pytest", "tests/test_app.py::test_one"]]),
        status=status,
    )


def sample_binding(base_sha="a" * 40, *, registered_root="/srv/projects/repo-1") -> RepositoryBinding:
    return RepositoryBinding(
        repository_id="repo-1",
        base_ref="main",
        base_sha=base_sha,
        registered_root=registered_root,
    )


def write_packet(path: Path, *, status: str, verdict: str, head_sha: str = "b" * 40, last_error: str | None = None) -> None:
    payload = {
        "change_id": "p1--wu-1",
        "repository_id": "repo-1",
        "registered_root": "/srv/projects/repo-1",
        "base_ref": "main",
        "base_sha": "a" * 40,
        "branch": "rack/change/p1--wu-1",
        "worktree_path": "/srv/rack-ai/worktrees/p1--wu-1",
        "task": "Implement one bounded behavior.",
        "allowed_paths": ["src/app.py"],
        "changed_paths": ["src/app.py"],
        "git_status": "M src/app.py",
        "diff_stat": " src/app.py | 2 ++",
        "diff": "diff --git a/src/app.py b/src/app.py",
        "head_sha": head_sha,
        "commands": [],
        "required_artifacts": [],
        "implementer_output": "done",
        "acceptance_verdict": verdict,
        "status": status,
        "retention": "retained",
        "last_error": last_error,
    }
    path.write_text(json.dumps(payload), encoding="utf-8")


@pytest.mark.asyncio
async def test_gateway_returns_structured_success_and_uses_argument_array(monkeypatch, tmp_path):
    captured: dict[str, object] = {}

    async def fake_exec(*args, **kwargs):
        captured["args"] = args
        captured["kwargs"] = kwargs
        spec_path = Path(args[7])
        captured["spec_path"] = spec_path
        captured["payload"] = json.loads(spec_path.read_text(encoding="utf-8"))
        packet_path = tmp_path / "packet.json"
        write_packet(packet_path, status="checks_passed", verdict="approved", head_sha="b" * 40)
        stdout = "\n".join(
            [
                "change_id: p1--wu-1",
                "branch: rack/change/p1--wu-1",
                "worktree: /srv/rack-ai/worktrees/p1--wu-1",
                "base_sha: " + "a" * 40,
                "status: checks_passed",
                "acceptance_verdict: approved",
                f"packet: {packet_path}",
            ]
        )
        return FakeProcess(stdout)

    monkeypatch.setattr("core.execution.rack_ai_cli_gateway.asyncio.create_subprocess_exec", fake_exec)

    gateway = RackAiCliExecutionGateway(
        "p1",
        RackAiCliConfig(executable="cargo", rack_ai_root="/srv/rack-ai", state_root="/srv/rack-ai"),
    )
    result = await gateway.execute(sample_unit(), sample_binding())

    assert result.accepted is True
    assert result.accepted_revision == "b" * 40
    assert result.change_id == "p1--wu-1"
    assert result.worktree_path == "/srv/rack-ai/worktrees/p1--wu-1"
    assert captured["payload"]["repository"]["base_sha"] == "a" * 40
    assert captured["payload"] == {
        "change_id": "p1--wu-1",
        "repository": {
            "id": "repo-1",
            "base_ref": "main",
            "base_sha": "a" * 40,
            "registered_root": "/srv/projects/repo-1",
        },
        "task": "Implement one bounded behavior.",
        "allowed_paths": ["src/app.py"],
        "acceptance": {
            "commands": [["python3", "-m", "pytest", "tests/test_app.py::test_one"]],
            "required_artifacts": [],
        },
        "limits": {
            "max_implementation_attempts": 2,
            "timeout_seconds": 900,
            "network": "disabled",
        },
    }
    assert captured["args"] == (
        "cargo",
        "run",
        "-q",
        "-p",
        "rack_ai_cli",
        "--",
        "change",
        str(captured["spec_path"]),
        "--repo-root",
        "/srv/rack-ai",
        "--state-root",
        "/srv/rack-ai",
    )
    assert not Path(captured["spec_path"]).exists()


@pytest.mark.asyncio
async def test_gateway_passes_updated_binding_base_sha(monkeypatch, tmp_path):
    captured: dict[str, object] = {}

    async def fake_exec(*args, **_kwargs):
        spec_path = Path(args[7])
        captured["payload"] = json.loads(spec_path.read_text(encoding="utf-8"))
        packet_path = tmp_path / "packet.json"
        write_packet(packet_path, status="checks_passed", verdict="approved", head_sha="c" * 40)
        stdout = "\n".join(
            [
                "change_id: p1--wu-1",
                "status: checks_passed",
                "acceptance_verdict: approved",
                f"packet: {packet_path}",
            ]
        )
        return FakeProcess(stdout)

    monkeypatch.setattr("core.execution.rack_ai_cli_gateway.asyncio.create_subprocess_exec", fake_exec)
    gateway = RackAiCliExecutionGateway("p1")
    await gateway.execute(sample_unit(), sample_binding(base_sha="b" * 40))
    assert captured["payload"]["repository"]["base_sha"] == "b" * 40


@pytest.mark.asyncio
async def test_gateway_returns_structured_rejection_even_on_nonzero_exit(monkeypatch, tmp_path):
    async def fake_exec(*_args, **_kwargs):
        packet_path = tmp_path / "packet.json"
        write_packet(
            packet_path,
            status="checks_failed",
            verdict="rejected",
            last_error="acceptance command failed",
        )
        stdout = "\n".join(
            [
                "change_id: p1--wu-1",
                "status: checks_failed",
                "acceptance_verdict: rejected",
                f"packet: {packet_path}",
            ]
        )
        return FakeProcess(stdout, returncode=1)

    monkeypatch.setattr("core.execution.rack_ai_cli_gateway.asyncio.create_subprocess_exec", fake_exec)

    gateway = RackAiCliExecutionGateway("p1")
    result = await gateway.execute(sample_unit(), sample_binding())

    assert result.accepted is False
    assert result.status == "checks_failed"
    assert result.error == "acceptance command failed"


@pytest.mark.asyncio
async def test_gateway_preserves_structured_failed_status(monkeypatch, tmp_path):
    async def fake_exec(*_args, **_kwargs):
        packet_path = tmp_path / "packet.json"
        write_packet(packet_path, status="failed", verdict="rejected")
        stdout = "\n".join(
            [
                "change_id: p1--wu-1",
                "status: failed",
                "acceptance_verdict: rejected",
                f"packet: {packet_path}",
            ]
        )
        return FakeProcess(stdout, returncode=1)

    monkeypatch.setattr("core.execution.rack_ai_cli_gateway.asyncio.create_subprocess_exec", fake_exec)

    gateway = RackAiCliExecutionGateway("p1")
    result = await gateway.execute(sample_unit(), sample_binding())

    assert result.accepted is False
    assert result.status == "failed"


@pytest.mark.asyncio
async def test_gateway_raises_on_nonzero_exit_without_usable_summary(monkeypatch):
    async def fake_exec(*_args, **_kwargs):
        return FakeProcess("", stderr="cargo failed", returncode=1)

    monkeypatch.setattr("core.execution.rack_ai_cli_gateway.asyncio.create_subprocess_exec", fake_exec)

    gateway = RackAiCliExecutionGateway("p1")
    with pytest.raises(RackAiCliTransportError, match="cargo failed"):
        await gateway.execute(sample_unit(), sample_binding())


@pytest.mark.asyncio
async def test_gateway_raises_on_empty_stdout(monkeypatch):
    async def fake_exec(*_args, **_kwargs):
        return FakeProcess("", stderr="no payload")

    monkeypatch.setattr("core.execution.rack_ai_cli_gateway.asyncio.create_subprocess_exec", fake_exec)

    gateway = RackAiCliExecutionGateway("p1")
    with pytest.raises(RackAiCliTransportError, match="returned no command summary"):
        await gateway.execute(sample_unit(), sample_binding())


@pytest.mark.asyncio
async def test_gateway_raises_on_malformed_packet_json(monkeypatch, tmp_path):
    async def fake_exec(*_args, **_kwargs):
        packet_path = tmp_path / "packet.json"
        packet_path.write_text("{not-json}", encoding="utf-8")
        stdout = "\n".join(
            [
                "change_id: p1--wu-1",
                "status: checks_passed",
                "acceptance_verdict: approved",
                f"packet: {packet_path}",
            ]
        )
        return FakeProcess(stdout, stderr="bad json")

    monkeypatch.setattr("core.execution.rack_ai_cli_gateway.asyncio.create_subprocess_exec", fake_exec)

    gateway = RackAiCliExecutionGateway("p1")
    with pytest.raises(RackAiCliTransportError, match="untrustworthy output"):
        await gateway.execute(sample_unit(), sample_binding())


@pytest.mark.asyncio
async def test_gateway_raises_on_missing_packet_path(monkeypatch):
    async def fake_exec(*_args, **_kwargs):
        stdout = "\n".join(
            [
                "change_id: p1--wu-1",
                "status: checks_passed",
                "acceptance_verdict: approved",
            ]
        )
        return FakeProcess(stdout, stderr="missing packet")

    monkeypatch.setattr("core.execution.rack_ai_cli_gateway.asyncio.create_subprocess_exec", fake_exec)

    gateway = RackAiCliExecutionGateway("p1")
    with pytest.raises(RackAiCliTransportError, match="missing field: packet"):
        await gateway.execute(sample_unit(), sample_binding())


@pytest.mark.asyncio
async def test_gateway_rejects_non_ready_units_before_subprocess(monkeypatch):
    called = False

    async def fake_exec(*_args, **_kwargs):
        nonlocal called
        called = True
        return FakeProcess("{}")

    monkeypatch.setattr("core.execution.rack_ai_cli_gateway.asyncio.create_subprocess_exec", fake_exec)

    gateway = RackAiCliExecutionGateway("p1")
    with pytest.raises(ValueError, match="marked ready for execution"):
        await gateway.execute(sample_unit(status=WorkUnitStatus.PLANNED), sample_binding())
    assert called is False
