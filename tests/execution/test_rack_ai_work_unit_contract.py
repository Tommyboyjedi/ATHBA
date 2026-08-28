import pytest

from core.development.work_unit import AcceptanceContract, DevelopmentWorkUnit, WorkUnitStatus
from core.execution.rack_ai_contract import (
    RepositoryBinding,
    find_forbidden_resource_selection_keys,
    parse_rack_ai_result,
    to_rack_ai_request,
)


def test_work_unit_readiness_requires_ready_state_and_dependencies():
    unit = DevelopmentWorkUnit(
        id="wu-2",
        project_id="p1",
        parent_ticket_id="t1",
        objective="implement one bounded behavior",
        allowed_paths=["src/app.py"],
        acceptance=AcceptanceContract(commands=[["pytest", "tests/test_app.py::test_one"]]),
        depends_on=["wu-1"],
    )
    assert not unit.is_ready(set())
    ready_unit = DevelopmentWorkUnit(
        id="wu-2",
        project_id="p1",
        parent_ticket_id="t1",
        objective="implement one bounded behavior",
        allowed_paths=["src/app.py"],
        acceptance=AcceptanceContract(commands=[["pytest", "tests/test_app.py::test_one"]]),
        depends_on=["wu-1"],
        status=WorkUnitStatus.READY,
    )
    assert not ready_unit.is_ready(set())
    assert ready_unit.is_ready({"wu-1"})


def test_work_unit_rejects_invalid_dependency_and_network_values():
    with pytest.raises(ValueError, match="cannot depend on itself"):
        DevelopmentWorkUnit(
            id="wu-1",
            project_id="p1",
            parent_ticket_id="t1",
            objective="objective",
            allowed_paths=["src/app.py"],
            acceptance=AcceptanceContract(commands=[["pytest", "tests/test_app.py"]]),
            depends_on=["wu-1"],
        )
    with pytest.raises(ValueError, match="unsupported work unit network policy"):
        DevelopmentWorkUnit(
            id="wu-1",
            project_id="p1",
            parent_ticket_id="t1",
            objective="objective",
            allowed_paths=["src/app.py"],
            acceptance=AcceptanceContract(commands=[["pytest", "tests/test_app.py"]]),
            network="enabled",
        )


def test_rack_ai_request_matches_pr22_contract_shape():
    unit = DevelopmentWorkUnit(
        id="adaptos-001",
        project_id="adaptos",
        parent_ticket_id="ticket-1",
        objective="Implement TicketStore::save(path) for one open ticket.",
        allowed_paths=["src/lib.rs"],
        acceptance=AcceptanceContract(
            commands=[["cargo", "test", "save_single_open_ticket"]],
            required_artifacts=["src/lib.rs"],
        ),
        status=WorkUnitStatus.READY,
    )
    request = to_rack_ai_request(
        "adaptos",
        RepositoryBinding(
            repository_id="adaptos",
            base_ref="main",
            base_sha="a" * 40,
            registered_root="/srv/projects/adaptos",
        ),
        unit,
    )
    assert request == {
        "version": "rack-ai/work-unit/v1",
        "workload": {"id": "adaptos", "kind": "application-development"},
        "repository": {
            "id": "adaptos",
            "base_ref": "main",
            "base_sha": "a" * 40,
            "registered_root": "/srv/projects/adaptos",
        },
        "work_unit": {
            "id": "adaptos-001",
            "objective": "Implement TicketStore::save(path) for one open ticket.",
            "allowed_paths": ["src/lib.rs"],
            "acceptance": {
                "commands": [["cargo", "test", "save_single_open_ticket"]],
                "required_artifacts": ["src/lib.rs"],
            },
            "readiness": {"ready": True, "depends_on": []},
            "requirements": {
                "capability": "implementation",
                "complexity": "small",
                "requires_large_context": False,
            },
            "limits": {
                "max_implementation_attempts": 2,
                "timeout_seconds": 900,
                "network": "disabled",
            },
        },
    }


def test_rack_ai_request_rejects_non_ready_units():
    unit = DevelopmentWorkUnit(
        id="wu-1",
        project_id="p1",
        parent_ticket_id="t1",
        objective="implement one bounded behavior",
        allowed_paths=["src/app.py"],
        acceptance=AcceptanceContract(commands=[["pytest", "tests/test_app.py::test_one"]]),
    )
    with pytest.raises(ValueError, match="marked ready for execution"):
        to_rack_ai_request(
            "p1",
            RepositoryBinding(repository_id="repo", base_ref="main", base_sha="a" * 40),
            unit,
        )


def test_rack_ai_request_structurally_blocks_physical_resource_keys():
    unit = DevelopmentWorkUnit(
        id="wu-1",
        project_id="p1",
        parent_ticket_id="t1",
        objective="implement one bounded behavior",
        allowed_paths=["src/app.py"],
        acceptance=AcceptanceContract(commands=[["pytest", "tests/test_app.py::test_one"]]),
        status=WorkUnitStatus.READY,
    )
    request = to_rack_ai_request(
        "p1",
        RepositoryBinding(repository_id="repo", base_ref="main", base_sha="a" * 40),
        unit,
    )
    assert find_forbidden_resource_selection_keys(request) == []
    leaked = {
        "work_unit": {
            "requirements": {
                "complexity": "small",
                "selected_worker_id": "local-coder",
                "placement": {"gpu_ids": ["gpu-2060"]},
            }
        }
    }
    assert find_forbidden_resource_selection_keys(leaked) == [
        "work_unit.requirements.selected_worker_id",
        "work_unit.requirements.placement.gpu_ids",
    ]


def test_parse_rack_ai_result_accepts_current_pr22_vocabulary():
    attempt = parse_rack_ai_result(
        {
            "workload_id": "adaptos",
            "work_unit_id": "adaptos-001",
            "change_id": "adaptos--adaptos-001",
            "selected_worker_id": "local-coder",
            "placement": {
                "worker_ids": ["local-coder"],
                "resource_ids": ["gpu-2060"],
                "model_ids": ["coder-model"],
                "backends": ["jcode"],
            },
            "status": "checks_passed",
            "acceptance_verdict": "approved",
            "branch": "rack/change/adaptos--adaptos-001",
            "worktree_path": "/srv/rack-ai/worktrees/adaptos",
            "packet_path": "/srv/rack-ai/state/packet.json",
        }
    )
    assert attempt.accepted is True
    assert attempt.status == "checks_passed"
    assert attempt.selected_worker_id == "local-coder"
    assert attempt.placement == {
        "worker_ids": ["local-coder"],
        "resource_ids": ["gpu-2060"],
        "model_ids": ["coder-model"],
        "backends": ["jcode"],
    }
    assert attempt.accepted_revision is None


def test_parse_rack_ai_result_preserves_structured_non_acceptance_outcomes():
    rejected = parse_rack_ai_result(
        {
            "work_unit_id": "wu-2",
            "change_id": "p1--wu-2",
            "status": "checks_failed",
            "acceptance_verdict": "rejected",
            "last_error": "acceptance command failed",
        }
    )
    blocked = parse_rack_ai_result(
        {
            "work_unit_id": "wu-3",
            "change_id": "p1--wu-3",
            "status": "blocked",
            "acceptance_verdict": "rejected",
        }
    )
    assert rejected.accepted is False
    assert rejected.error == "acceptance command failed"
    assert blocked.accepted is False
    assert blocked.status == "blocked"


def test_parse_rack_ai_result_tolerates_missing_optional_evidence_fields():
    attempt = parse_rack_ai_result(
        {
            "work_unit_id": "wu-4",
            "change_id": "p1--wu-4",
            "status": "failed",
            "acceptance_verdict": "rejected",
        }
    )
    assert attempt.selected_worker_id is None
    assert attempt.placement is None
    assert attempt.branch is None
    assert attempt.packet_path is None


def test_parse_rack_ai_result_requires_identity_and_supported_verdict():
    with pytest.raises(ValueError, match="missing required field: work_unit_id"):
        parse_rack_ai_result(
            {
                "change_id": "p1--wu-1",
                "status": "checks_passed",
                "acceptance_verdict": "approved",
            }
        )
    with pytest.raises(ValueError, match="unsupported Rack AI acceptance verdict"):
        parse_rack_ai_result(
            {
                "work_unit_id": "wu-1",
                "change_id": "p1--wu-1",
                "status": "checks_passed",
                "acceptance_verdict": "accepted",
            }
        )


def test_parse_rack_ai_result_exposes_future_accepted_revision_when_present():
    attempt = parse_rack_ai_result(
        {
            "work_unit_id": "wu-5",
            "change_id": "p1--wu-5",
            "status": "checks_passed",
            "acceptance_verdict": "approved",
            "accepted_head_sha": "b" * 40,
        }
    )
    assert attempt.accepted_revision == "b" * 40
