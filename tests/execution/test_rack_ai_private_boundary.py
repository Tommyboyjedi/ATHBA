from __future__ import annotations

import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest

from core.development.athba_workspace_routing import (
    AthbaExecutionProfile,
    AthbaModelWorkKind,
    AthbaOutboundPriority,
    AthbaWorkspaceIdentity,
    GenericModelCapability,
    WorkspaceComplexity,
)
from core.development.work_unit import AcceptanceContract, DevelopmentWorkUnit, WorkUnitStatus
from core.execution.profiled_workspace_gateway import ProfiledWorkspaceExecutionGateway, ProfiledWorkspaceGatewayDependencies
from core.execution.rack_ai_request import RepositoryBinding
from core.execution.unsupported_workspace_execution import UnsupportedWorkspaceExecutionPort
from core.execution.workspace_execution_port import WorkspaceExecutionRequest, WorkspaceExecutionResult, WorkspaceExecutionStatus
from core.development.athba_workspace_routing import AthbaExecutionProfileResolver


DELETED_PRIVATE_MODULES = (
    "core.execution.rack_ai_workspace_runtime",
    "core.execution.rack_ai_workspace_connector",
    "core.execution.rack_ai_cli_transport",
    "core.execution.rack_ai_cli_gateway",
    "core.execution.rack_ai_result",
)


def workspace_request() -> WorkspaceExecutionRequest:
    return WorkspaceExecutionRequest(
        AthbaWorkspaceIdentity("work", "submission", "attempt"),
        AthbaExecutionProfile(
            frozenset({GenericModelCapability.CODING}),
            WorkspaceComplexity.SMALL,
            False,
            AthbaOutboundPriority.LOW,
            300,
        ),
        RepositoryBinding("repo", "main", "a" * 40, registered_root="/srv/rack-ai/private/repo"),
        ("src/app.py",),
        "disabled",
        (("python", "-m", "pytest"),),
        ("src/app.py",),
        "bounded objective",
    )


def test_private_workspace_and_cli_adapters_are_not_importable():
    for name in DELETED_PRIVATE_MODULES:
        assert importlib.util.find_spec(name) is None


def test_unsupported_workspace_port_does_not_read_private_paths(monkeypatch):
    private_reads = []
    original = Path.read_text

    def guarded_read_text(self, *args, **kwargs):
        if str(self).startswith("/srv/rack-ai"):
            private_reads.append(str(self))
            raise AssertionError(f"private RackAI path read: {self}")
        return original(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", guarded_read_text)
    result = UnsupportedWorkspaceExecutionPort().submit_workspace_change(workspace_request())

    assert result.status is WorkspaceExecutionStatus.CAPABILITY_UNAVAILABLE
    assert private_reads == []


@pytest.mark.asyncio
async def test_profiled_gateway_drops_private_paths_and_executor_provenance_from_port_result():
    class Port:
        def submit_workspace_change(self, request):
            return WorkspaceExecutionResult(
                request.identity,
                WorkspaceExecutionStatus.ACCEPTED,
                accepted_revision="b" * 40,
                worktree_ref="/srv/rack-ai/state/private-worktree",
                evidence_refs=("public-evidence-ref",),
                selected_worker_id="local-coder",
                execution_provenance={
                    "worker_id": "local-coder",
                    "worker_kind": "jcode",
                    "backend": "jcode",
                    "resource_id": "gpu-2060",
                },
            )

    unit = DevelopmentWorkUnit(
        "submission",
        "project",
        "ticket",
        "objective",
        ["src/app.py"],
        AcceptanceContract([["python", "-m", "pytest"]]),
        model_work_kind=AthbaModelWorkKind.FRONTIER_IMPLEMENTATION,
        workspace_identity=AthbaWorkspaceIdentity("work", "submission", "attempt"),
        status=WorkUnitStatus.READY,
    )

    result = await ProfiledWorkspaceExecutionGateway(
        ProfiledWorkspaceGatewayDependencies(Port(), AthbaExecutionProfileResolver())
    ).execute(unit, RepositoryBinding("repo", "main", "a" * 40))

    assert result.accepted is True
    assert result.worktree_path is None
    assert result.selected_worker_id is None
    assert result.worker_provenance is None
    assert result.evidence_location == "public-evidence-ref"


def test_live_composition_does_not_inspect_rackai_checkout(monkeypatch, tmp_path):
    from core.development import strict_tdd_live_run_composition as composition_module
    from core.development.strict_tdd_live_run_composition import (
        StrictTddLiveRunCompositionFactory,
        StrictTddLiveRunCompositionRequest,
        StrictTddLiveRunConfiguration,
    )
    from core.execution.reasoning_gateway import ReasoningGateway, ReasoningResult
    from core.execution.work_unit_gateway import WorkUnitExecutionResult

    calls = []

    def guarded_run(args, **kwargs):
        calls.append(args)
        assert "/srv/rack-ai" not in args
        return SimpleNamespace(stdout="athba-sha\n")

    class Reasoning(ReasoningGateway):
        async def reason(self, request):
            return ReasoningResult("{}", "fake", "fake")

    class Gateway:
        async def execute(self, work_unit, repository_binding):
            return WorkUnitExecutionResult(work_unit.id, False, "capability_unavailable")

    captured = []

    def build(_, request):
        captured.append(request)
        return SimpleNamespace(application=SimpleNamespace())

    monkeypatch.setattr(composition_module, "run", guarded_run)
    monkeypatch.setattr(composition_module.StrictTddFeatureCompositionFactory, "build", build)
    preflight = SimpleNamespace(check=lambda _: SimpleNamespace(kind="green"))
    config = StrictTddLiveRunConfiguration(
        tmp_path / "state",
        tmp_path / "evidence",
        tmp_path / "repo",
        "project",
        athba_repository_root=tmp_path / "athba-source",
    )

    result = StrictTddLiveRunCompositionFactory(preflight=preflight).build(
        StrictTddLiveRunCompositionRequest(config, Reasoning(), Gateway())
    )

    assert result.athba_revision == "athba-sha"
    assert result.rack_ai_revision == "rack-ai-runtime-revision-unavailable"
    assert calls == [("git", "-C", str(tmp_path / "athba-source"), "rev-parse", "HEAD")]
    assert captured
