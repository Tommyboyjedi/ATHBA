from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from core.agents.behaviors.tester.execute_tests_behavior import ExecuteTestsBehavior
from core.agents.interfaces import BehaviorExecution
from core.dataclasses.llm_intent import LlmIntent
from core.dataclasses.ticket_model import TicketModel
from core.services.service_requests import TestRunRequest as RunTestsRequest


class RecordingTestService:
    def __init__(self, result: dict):
        self.result = result
        self.requests: list[RunTestsRequest] = []

    async def run_tests(self, request: RunTestsRequest) -> dict:
        self.requests.append(request)
        return dict(self.result)


@pytest.mark.asyncio
async def test_execute_tests_behavior_uses_test_run_request_boundary():
    ticket = TicketModel(
        id="ticket-1",
        project_id="project-123",
        title="Run the reservation tests",
        branch_name="feature/reservation-tests",
        test_files=["tests/test_reservation_book.py"],
    )
    service = RecordingTestService(
        {
            "status": "success",
            "passed": 3,
            "failed": 0,
            "errors": 0,
            "skipped": 0,
            "total": 3,
            "pass_rate": 1.0,
            "output": "3 passed in 0.12s",
            "duration": 0.12,
        }
    )
    agent = SimpleNamespace(
        name="Tester",
        session=SimpleNamespace(current_ticket="ticket-1"),
        ticket_repo=SimpleNamespace(
            get_ticket_by_id=AsyncMock(return_value=ticket),
            update=AsyncMock(),
        ),
        git_service=SimpleNamespace(checkout_branch=AsyncMock()),
        test_service=service,
        project=SimpleNamespace(id="project-123"),
    )
    intent = LlmIntent(response="Run the tests.", intent="execute_tests", agents_routing=[], entities={})

    result = await ExecuteTestsBehavior().run(
        BehaviorExecution(agent=agent, message="run tests", intent=intent)
    )

    assert result is not None
    assert len(service.requests) == 1
    request = service.requests[0]
    assert isinstance(request, RunTestsRequest)
    assert request.project_id == "project-123"
    assert request.test_files == ["tests/test_reservation_book.py"]
    assert request.verbose is True
    agent.git_service.checkout_branch.assert_awaited_once_with("project-123", "feature/reservation-tests")
    agent.ticket_repo.update.assert_awaited_once_with(ticket)
    assert "Test Execution Complete" in result[0].content
