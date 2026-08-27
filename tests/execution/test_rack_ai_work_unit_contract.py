from core.development.work_unit import AcceptanceContract, DevelopmentWorkUnit
from core.execution.rack_ai_contract import RepositoryBinding, to_rack_ai_request


def test_work_unit_readiness_requires_all_dependencies():
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
    assert unit.is_ready({"wu-1"})


def test_rack_ai_request_never_contains_physical_resource_selection():
    unit = DevelopmentWorkUnit(
        id="wu-1",
        project_id="p1",
        parent_ticket_id="t1",
        objective="implement one bounded behavior",
        allowed_paths=["src/app.py"],
        acceptance=AcceptanceContract(commands=[["pytest", "tests/test_app.py::test_one"]]),
    )
    request = to_rack_ai_request(
        "p1",
        RepositoryBinding(repository_id="repo", base_ref="main", base_sha="a" * 40),
        unit,
    )
    serialized = str(request).lower()
    assert '"gpu"' not in serialized
    assert '"model"' not in serialized
    assert '"worker"' not in serialized
    assert request["version"] == "rack-ai/work-unit/v1"
