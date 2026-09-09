from __future__ import annotations

from dataclasses import replace

import pytest

from core.development.athba_workspace_routing import (
    AthbaExecutionProfileResolver,
    AthbaModelWorkKind,
    AthbaOutboundPriority,
    AthbaProfileResolutionRequest,
    AthbaWorkspaceIdentity,
)
from core.execution.rack_ai_request import RepositoryBinding
from core.execution.rack_ai_workspace_connector import (
    RACK_AI_WORK_UNIT_VERSION,
    RackAiWorkspaceConnector,
)
from core.execution.workspace_execution_port import (
    WorkspaceExecutionRequest,
    WorkspaceExecutionStatus,
)


class CapturingTransport:
    def __init__(self, response: dict[str, object] | None = None):
        self.payload: dict[str, object] | None = None
        self.response = response

    def submit(self, payload: dict[str, object]) -> dict[str, object]:
        self.payload = payload
        if self.response is not None:
            return self.response
        routing = payload["work_unit"]["routing"]
        assert isinstance(routing, dict)
        submission_id = routing["submission_id"]
        return approved_packet(str(submission_id))


def approved_packet(submission_id: str) -> dict[str, object]:
    return {
        "submission_id": submission_id,
        "status": "checks_passed",
        "acceptance_verdict": "approved",
        "head_sha": "b" * 40,
        "branch": "rack/change/opaque",
        "worktree_path": "/srv/rack-ai/state/workspaces/opaque",
        "changed_paths": ["src/widget.py"],
        "packet_path": "/srv/rack-ai/state/changes/opaque/review-packet.json",
        "selection_decision": {
            "submission_id": submission_id,
            "selected_worker_id": "selected-generic-worker",
            "decision_id": "decision-opaque",
        },
        "worker_provenance": {
            "worker_id": "selected-generic-worker",
            "provider_profile": "opaque-provider",
        },
    }


def request_for(kind: AthbaModelWorkKind, *, submission_id: str = "submission") -> WorkspaceExecutionRequest:
    profile = AthbaExecutionProfileResolver().resolve(AthbaProfileResolutionRequest(kind, 300))
    assert profile is not None
    return WorkspaceExecutionRequest(
        identity=AthbaWorkspaceIdentity("stable-work", submission_id, "stable-key"),
        profile=profile,
        repository=RepositoryBinding("fixture", "main", "a" * 40, "/srv/ATHBA/state/projects/fixture", ["python"]),
        allowed_writable_paths=("src/widget.py",),
        network_policy="disabled",
        acceptance_commands=(("python3", "-m", "pytest", "tests/test_widget.py"),),
        required_artifacts=("src/widget.py",),
        objective="Make one bounded neutral change.",
    )


@pytest.mark.parametrize(
    ("kind", "capabilities", "complexity", "priority"),
    [
        (AthbaModelWorkKind.COMPLETE_SCENARIO_AUTHORING, ["reasoning", "coding"], "medium", "medium"),
        (AthbaModelWorkKind.FRONTIER_IMPLEMENTATION, ["coding"], "small", "low"),
        (AthbaModelWorkKind.STRONGER_FRONTIER_FALLBACK, ["reasoning", "coding"], "medium", "medium"),
    ],
)
def test_connector_serializes_profile_at_exact_v2_locations(kind, capabilities, complexity, priority):
    transport = CapturingTransport()
    RackAiWorkspaceConnector(transport).submit_workspace_change(request_for(kind))
    assert transport.payload is not None
    payload = transport.payload
    routing = payload["work_unit"]["routing"]
    requirements = payload["work_unit"]["requirements"]
    assert payload["version"] == RACK_AI_WORK_UNIT_VERSION
    assert routing["source_system"] == "athba"
    assert routing["required_capabilities"] == capabilities
    assert routing["priority"] == priority
    assert requirements["complexity"] == complexity
    assert requirements["requires_large_context"] is False


def test_v2_wire_preserves_identity_and_excludes_athba_dependencies_and_resources():
    transport = CapturingTransport()
    RackAiWorkspaceConnector(transport).submit_workspace_change(request_for(AthbaModelWorkKind.FRONTIER_IMPLEMENTATION))
    assert transport.payload is not None
    payload = transport.payload
    routing = payload["work_unit"]["routing"]
    assert routing["work_id"] == "stable-work"
    assert routing["submission_id"] == "submission"
    assert routing["idempotency_key"] == "stable-key"
    assert "depends_on" not in payload["work_unit"]
    wire = repr(payload).lower()
    assert "selected_worker_id" not in wire
    assert "gpu" not in wire
    assert "jcode" not in wire


@pytest.mark.parametrize("priority", ("high", "paramount"))
def test_connector_rejects_malformed_priority_before_transport_submission(priority):
    transport = CapturingTransport()
    request = request_for(AthbaModelWorkKind.FRONTIER_IMPLEMENTATION)
    object.__setattr__(request.profile, "priority", priority)
    with pytest.raises(ValueError, match="must not exceed medium"):
        RackAiWorkspaceConnector(transport).submit_workspace_change(request)
    assert transport.payload is None


@pytest.mark.parametrize(
    ("status", "verdict", "expected"),
    [
        ("checks_passed", "approved", WorkspaceExecutionStatus.ACCEPTED),
        ("checks_failed", "rejected", WorkspaceExecutionStatus.REJECTED),
        ("capability_unavailable", None, WorkspaceExecutionStatus.CAPABILITY_UNAVAILABLE),
        ("temporarily_unavailable", None, WorkspaceExecutionStatus.TEMPORARILY_UNAVAILABLE),
        ("timeout", None, WorkspaceExecutionStatus.TIMEOUT),
    ],
)
def test_connector_translates_generic_terminal_outcomes_without_athba_reinterpretation(status, verdict, expected):
    response = {"submission_id": "submission", "status": status, "generic_failure": "generic failure"}
    if verdict is not None:
        response["acceptance_verdict"] = verdict
    result = RackAiWorkspaceConnector(CapturingTransport(response)).submit_workspace_change(request_for(AthbaModelWorkKind.FRONTIER_IMPLEMENTATION))
    assert result.status == expected
    assert result.generic_failure == "generic failure"


def test_connector_retains_v2_evidence_and_validates_selection_provenance_match():
    result = RackAiWorkspaceConnector(CapturingTransport()).submit_workspace_change(request_for(AthbaModelWorkKind.COMPLETE_SCENARIO_AUTHORING))
    assert result.accepted_revision == "b" * 40
    assert result.candidate_revision == "b" * 40
    assert result.branch == "rack/change/opaque"
    assert result.changed_paths == ("src/widget.py",)
    assert result.acceptance_verdict == "approved"
    assert result.selection_decision is not None
    assert result.execution_provenance is not None
    assert result.selected_worker_id == result.executed_worker_id
    assert result.evidence_refs == ("/srv/rack-ai/state/changes/opaque/review-packet.json",)


def test_connector_keeps_historical_top_level_evidence_compatible_when_v2_evidence_is_absent():
    response = {
        "submission_id": "submission",
        "status": "accepted",
        "accepted_revision": "c" * 40,
        "selected_worker_id": "legacy-worker",
        "executed_worker_id": "legacy-worker",
    }
    result = RackAiWorkspaceConnector(CapturingTransport(response)).submit_workspace_change(request_for(AthbaModelWorkKind.FRONTIER_IMPLEMENTATION))
    assert result.status == WorkspaceExecutionStatus.ACCEPTED
    assert result.selection_decision is None
    assert result.execution_provenance is None
