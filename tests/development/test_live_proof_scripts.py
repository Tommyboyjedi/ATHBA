import asyncio
import subprocess
from pathlib import Path
from types import SimpleNamespace

from scripts.run_pr17_independent_reservation_book import (
    PersistingExecutionGateway,
    build_live_reasoning_gateway as build_proof_gateway,
    sync_project_to_semantic_revision,
)
from scripts.run_specification_gatekeeper_probe import build_live_reasoning_gateway as build_probe_gateway
from core.development.behavior_contract_coordinator import CoordinatorDependencies
from core.development.project_environment import ProjectEnvironmentService
from core.development.python_test_runtime import PythonPytestRuntime
from core.development.specification_gatekeeper import SpecificationGapTddAdapter, SpecificationGatekeeper
from core.execution.rack_ai_contract import RepositoryBinding
from core.execution.work_unit_gateway import WorkUnitExecutionResult


class _DummyExecutionGateway:
    async def execute(self, work_unit, repository_binding):  # pragma: no cover - not called
        raise AssertionError("execute should not be called in this wiring test")


class _StubRequest:
    def __init__(self, change_id: str):
        self.change_id = change_id
        self.limits = SimpleNamespace(timeout_seconds=123)

    def to_dict(self) -> dict[str, object]:
        return {"change_id": self.change_id, "limits": {"timeout_seconds": 123}}


class _StubRequestFactory:
    def __init__(self, change_id: str):
        self.change_id = change_id

    def build(self, _request):
        return _StubRequest(self.change_id)


class _StubWatchdog:
    def deadline_seconds(self, _request) -> int:
        return 321


class _StubDelegate:
    def __init__(self, result: WorkUnitExecutionResult, state_root: Path):
        self.result = result
        self.workload_id = "proof-project"
        self.request_factory = _StubRequestFactory(result.change_id or "change-1")
        self.config = SimpleNamespace(state_root=str(state_root))
        self.transport = SimpleNamespace(watchdog=_StubWatchdog())

    async def execute(self, work_unit, repository_binding):
        return self.result


def test_live_proof_gateways_use_provider_retry_policy(monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("OPENAI_API_BASE", "http://127.0.0.1:8017/v1")
    monkeypatch.delenv("OPENAI_ORG", raising=False)

    proof_gateway = build_proof_gateway("local-primary")
    probe_gateway = build_probe_gateway("local-primary")

    assert proof_gateway.delegate.provider.policy.timeout == 300.0
    assert proof_gateway.delegate.provider.policy.max_retries == 1
    assert proof_gateway.delegate.provider.policy.backoff_factor == 2.0
    assert proof_gateway.delegate.model == "local-primary"

    assert probe_gateway.delegate.provider.policy.timeout == 300.0
    assert probe_gateway.delegate.provider.policy.max_retries == 1
    assert probe_gateway.delegate.provider.policy.backoff_factor == 2.0
    assert probe_gateway.delegate.model == "local-primary"


def test_pr17_proof_coordinator_dependencies_include_gatekeeper(monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("OPENAI_API_BASE", "http://127.0.0.1:8017/v1")
    gateway = build_proof_gateway("local-primary")
    runtime = PythonPytestRuntime("/srv/ATHBA/.venv/bin/python")

    dependencies = CoordinatorDependencies(
        execution_gateway=_DummyExecutionGateway(),
        reasoning_gateway=gateway,
        repository_binding=RepositoryBinding(
            repository_id="proof-project",
            base_ref="main",
            base_sha="a" * 40,
            registered_root="/tmp/proof-project",
            environment_resources=[],
        ),
        gatekeeper=SpecificationGatekeeper(gateway),
        gap_adapter=SpecificationGapTddAdapter(),
    )

    assert isinstance(dependencies.gatekeeper, SpecificationGatekeeper)
    assert isinstance(dependencies.gap_adapter, SpecificationGapTddAdapter)
    assert runtime.pytest_command("tests/test_reservation_book.py")


def test_persisting_execution_gateway_records_mechanical_acceptance_without_promoting(tmp_path) -> None:
    result = WorkUnitExecutionResult(
        work_unit_id="red-1",
        accepted=True,
        status="checks_passed",
        accepted_revision="b" * 40,
        change_id="change-1",
    )
    gateway = PersistingExecutionGateway(_StubDelegate(result, tmp_path))
    returned = asyncio.run(
        gateway.execute(
            object(),
            RepositoryBinding(
                repository_id="proof-project",
                base_ref="main",
                base_sha="a" * 40,
                registered_root=str(tmp_path),
                environment_resources=[],
            ),
        )
    )

    assert returned == result
    assert gateway.accepted_revisions == ["b" * 40]
    assert len(gateway.rack_ai_events) == 1
    assert gateway.rack_ai_events[0]["request"] == {
        "change_id": "change-1",
        "limits": {"timeout_seconds": 123},
    }
    assert gateway.rack_ai_events[0]["result"]["accepted_revision"] == "b" * 40


def test_sync_project_to_semantic_revision_promotes_only_semantic_base(tmp_path) -> None:
    service = ProjectEnvironmentService(tmp_path)
    project = service.create_or_load_python_project("proof-project")
    repo_root = Path(project.repository_root)
    subprocess.run(["git", "switch", "-c", "candidate"], cwd=repo_root, check=True)
    (repo_root / "marker.txt").write_text("semantic approval\n", encoding="utf-8")
    subprocess.run(["git", "add", "marker.txt"], cwd=repo_root, check=True)
    subprocess.run(
        ["git", "-c", "user.name=ATHBA", "-c", "user.email=athba@example.test", "commit", "-qm", "semantic"],
        cwd=repo_root,
        check=True,
    )
    semantic_revision = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    subprocess.run(["git", "switch", "main"], cwd=repo_root, check=True)

    unchanged = sync_project_to_semantic_revision(service, project.project_id, project.trusted_base_sha)
    promoted = sync_project_to_semantic_revision(service, project.project_id, semantic_revision)

    assert unchanged.trusted_base_sha == project.trusted_base_sha
    assert promoted.trusted_base_sha == semantic_revision
    assert service.repo.load(project.project_id).trusted_base_sha == semantic_revision
