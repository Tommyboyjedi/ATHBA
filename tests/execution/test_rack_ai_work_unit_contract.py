import pytest

from core.development.work_unit import AcceptanceContract, DevelopmentWorkUnit, WorkUnitStatus
from core.execution.rack_ai_contract import (
    RepositoryBinding,
    find_forbidden_resource_selection_keys,
    to_rack_ai_request,
)


def test_work_unit_readiness_requires_ready_state_and_dependencies():
    unit = DevelopmentWorkUnit(
        id="wu-2",
        project_id="p1",
        parent_ticket_id="t1",
        objective="implement one bounded behavior",
        allowed_paths=["src/app.py"],
        acceptance=AcceptanceContract(commands=[["python3", "-m", "pytest", "tests/test_app.py::test_one"]]),
        depends_on=["wu-1"],
    )
    assert not unit.is_ready(set())
    ready_unit = DevelopmentWorkUnit(
        id="wu-2",
        project_id="p1",
        parent_ticket_id="t1",
        objective="implement one bounded behavior",
        allowed_paths=["src/app.py"],
        acceptance=AcceptanceContract(commands=[["python3", "-m", "pytest", "tests/test_app.py::test_one"]]),
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
            acceptance=AcceptanceContract(commands=[["python3", "-m", "pytest", "tests/test_app.py"]]),
            depends_on=["wu-1"],
        )
    with pytest.raises(ValueError, match="unsupported work unit network policy"):
        DevelopmentWorkUnit(
            id="wu-1",
            project_id="p1",
            parent_ticket_id="t1",
            objective="objective",
            allowed_paths=["src/app.py"],
            acceptance=AcceptanceContract(commands=[["python3", "-m", "pytest", "tests/test_app.py"]]),
            network="enabled",
        )


def test_rack_ai_request_matches_current_change_contract_shape():
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
            environment_resources=["/srv/environments/adaptos"],
        ),
        unit,
    )
    assert request == {
        "change_id": "adaptos--adaptos-001",
        "repository": {
            "id": "adaptos",
            "base_ref": "main",
            "base_sha": "a" * 40,
            "root": "/srv/projects/adaptos",
        },
        "task": "Implement TicketStore::save(path) for one open ticket.",
        "allowed_paths": ["src/lib.rs"],
        "acceptance": {
            "commands": [["cargo", "test", "save_single_open_ticket"]],
            "required_artifacts": ["src/lib.rs"],
        },
        "limits": {
            "max_implementation_attempts": 2,
            "timeout_seconds": 900,
            "network": "disabled",
        },
        "environment_resources": ["/srv/environments/adaptos"],
    }


def test_rack_ai_request_rejects_non_ready_units():
    unit = DevelopmentWorkUnit(
        id="wu-1",
        project_id="p1",
        parent_ticket_id="t1",
        objective="implement one bounded behavior",
        allowed_paths=["src/app.py"],
        acceptance=AcceptanceContract(commands=[["python3", "-m", "pytest", "tests/test_app.py::test_one"]]),
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
        acceptance=AcceptanceContract(commands=[["python3", "-m", "pytest", "tests/test_app.py::test_one"]]),
        status=WorkUnitStatus.READY,
    )
    request = to_rack_ai_request(
        "p1",
        RepositoryBinding(repository_id="repo", base_ref="main", base_sha="a" * 40),
        unit,
    )
    assert find_forbidden_resource_selection_keys(request) == []
    leaked = {
        "task": {
            "selected_worker_id": "local-coder",
            "placement": {"gpu_ids": ["gpu-2060"]},
        }
    }
    assert find_forbidden_resource_selection_keys(leaked) == [
        "task.selected_worker_id",
        "task.placement.gpu_ids",
    ]


def test_repository_binding_round_trip_preserves_optional_fields_and_resources():
    restored = RepositoryBinding.from_dict(
        {
            "repository_id": "repo",
            "base_ref": "main",
            "base_sha": None,
            "registered_root": None,
            "environment_resources": ["/srv/environments/adaptos"],
        }
    )

    assert restored.base_sha is None
    assert restored.registered_root is None
    assert restored.environment_resources == ["/srv/environments/adaptos"]
    assert restored.to_dict() == {
        "repository_id": "repo",
        "base_ref": "main",
        "base_sha": None,
        "registered_root": None,
        "environment_resources": ["/srv/environments/adaptos"],
    }
