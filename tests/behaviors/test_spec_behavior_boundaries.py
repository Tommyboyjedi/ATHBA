from types import SimpleNamespace

import pytest

from core.agents.behaviors.spec.add_to_spec_behavior import AddToSpecBehavior
from core.agents.behaviors.spec.ask_a_question_behavior import AskAQuestionBehavior
from core.agents.behaviors.spec.change_spec_behavior import ChangeSpecBehavior
from core.agents.behaviors.spec.finalize_spec_behavior import FinalizeSpecBehavior
from core.agents.behaviors.spec.start_spec_behavior import StartSpecBehavior
from core.agents.interfaces import BehaviorExecution
from core.dataclasses.chat_message import ChatMessage
from core.dataclasses.llm_intent import LlmIntent
from core.datastore.repos.mongo_requests import MongoFindRequest, MongoUpdateRequest


def execution(intent_name: str, response: str = "response text") -> BehaviorExecution:
    return BehaviorExecution(
        agent=SimpleNamespace(name="Spec"),
        message="user input",
        intent=LlmIntent(response=response, intent=intent_name, agents_routing=[], entities={}),
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("behavior", "intent_name", "expected"),
    [
        (StartSpecBehavior(), "start_spec", "response text"),
        (AddToSpecBehavior(), "add_to_spec", "response text"),
        (AskAQuestionBehavior(), "ask_a_question", "response text"),
        (ChangeSpecBehavior(), "change_spec", "response text"),
    ],
)
async def test_spec_behaviors_run_on_active_intents(behavior, intent_name, expected):
    result = await behavior.run(execution(intent_name))

    assert result is not None
    assert isinstance(result[0], ChatMessage)
    assert result[0].sender == "Spec"
    assert expected in result[0].content


@pytest.mark.asyncio
async def test_finalize_spec_behavior_uses_canonical_repo_requests(monkeypatch):
    find_requests = []
    update_requests = []
    scheduled = []

    async def find(request):
        find_requests.append(request)
        return [{"version": 3, "created_at": "2026-08-30T00:00:00+00:00"}]

    async def update(request):
        update_requests.append(request)

    async def fake_run_architect(_session):
        return None

    def fake_create_task(coro):
        scheduled.append(coro)
        coro.close()
        return None

    monkeypatch.setattr("core.agents.behaviors.spec.finalize_spec_behavior.asyncio.create_task", fake_create_task)

    behavior = FinalizeSpecBehavior()
    monkeypatch.setattr(behavior, "_run_architect", fake_run_architect)
    agent = SimpleNamespace(
        name="Spec",
        session=SimpleNamespace(project_id="project-123"),
        spec_repo=SimpleNamespace(find=find, update=update),
    )

    result = await behavior.run(
        BehaviorExecution(
            agent=agent,
            message="finalize the spec",
            intent=LlmIntent(response="Finalize it.", intent="finalize_spec", agents_routing=[], entities={}),
        )
    )

    assert result is not None
    assert isinstance(find_requests[0], MongoFindRequest)
    assert find_requests[0].filter == {"project_id": "project-123"}
    assert find_requests[0].sort == [("version", -1)]
    assert find_requests[0].limit == 1
    assert isinstance(update_requests[0], MongoUpdateRequest)
    assert update_requests[0].filter == {"project_id": "project-123", "version": 3}
    assert update_requests[0].update["approved"] is True
    assert scheduled
    assert "finalized and approved" in result[0].content
