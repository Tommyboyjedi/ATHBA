import copy
from base64 import urlsafe_b64encode
from datetime import datetime
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from core.agents.agent_generator import AgentGenerator
from core.agents.behaviors.architect.analyze_spec_behavior import AnalyzeSpecBehavior
from core.agents.behaviors.architect.basic_reply_behavior import BasicReplyBehavior as ArchitectBasicReplyBehavior
from core.agents.behaviors.architect.refine_tickets_behavior import RefineTicketsBehavior
from core.agents.behaviors.developer.analyze_ticket_behavior import AnalyzeTicketBehavior
from core.agents.behaviors.developer.basic_reply_behavior import BasicReplyBehavior as DeveloperBasicReplyBehavior
from core.agents.behaviors.developer.claim_ticket_behavior import ClaimTicketBehavior
from core.agents.behaviors.developer.commit_code_behavior import CommitCodeBehavior
from core.agents.behaviors.developer.create_branch_behavior import CreateBranchBehavior
from core.agents.behaviors.developer.generate_code_behavior import GenerateCodeBehavior
from core.agents.behaviors.developer.request_review_behavior import RequestReviewBehavior
from core.agents.behaviors.pm.basic_reply_behavior import BasicReplyBehavior as PmBasicReplyBehavior
from core.agents.behaviors.pm.confirm_action_behavior import ConfirmActionBehavior
from core.agents.behaviors.pm.create_project_behavior import CreateProjectBehavior
from core.agents.behaviors.pm.delegate_to_spec_builder_behavior import DelegateToSpecBuilderBehavior
from core.agents.behaviors.pm.get_status_behavior import GetStatusBehavior
from core.agents.behaviors.pm.pause_project_behavior import PauseProjectBehavior
from core.agents.behaviors.pm.rename_project_behavior import RenameProjectBehavior
from core.agents.behaviors.pm.resume_project_behavior import ResumeProjectBehavior
from core.agents.behaviors.spec.add_to_spec_behavior import AddToSpecBehavior
from core.agents.behaviors.spec.ask_a_question_behavior import AskAQuestionBehavior
from core.agents.behaviors.spec.change_spec_behavior import ChangeSpecBehavior
from core.agents.behaviors.spec.finalize_spec_behavior import FinalizeSpecBehavior
from core.agents.behaviors.spec.start_spec_behavior import StartSpecBehavior
from core.agents.behaviors.tester.analyze_code_behavior import AnalyzeCodeBehavior
from core.agents.behaviors.tester.approve_code_behavior import ApproveCodeBehavior
from core.agents.behaviors.tester.basic_reply_behavior import BasicReplyBehavior as TesterBasicReplyBehavior
from core.agents.behaviors.tester.claim_review_ticket_behavior import ClaimReviewTicketBehavior
from core.agents.behaviors.tester.commit_test_behavior import CommitTestBehavior
from core.agents.behaviors.tester.execute_tests_behavior import ExecuteTestsBehavior
from core.agents.behaviors.tester.generate_test_behavior import GenerateTestBehavior
from core.agents.behaviors.tester.reject_code_behavior import RejectCodeBehavior
from core.agents.behaviors.tester.verify_pass_behavior import VerifyPassBehavior
from core.agents.interfaces import BehaviorExecution
from core.dataclasses.history_entry import HistoryEntry
from core.dataclasses.llm_intent import LlmIntent
from core.dataclasses.ticket_model import TicketModel
from llm_service.enums.etier import ETier


class FakeRequestSession(dict):
    def __init__(self):
        super().__init__()
        self.save_called = False

    def save(self):
        self.save_called = True


class FakeTicketRepo:
    def __init__(self, tickets):
        self._tickets = {ticket.id: ticket for ticket in tickets}

    async def list_all(self, _project_id):
        return list(self._tickets.values())

    async def get(self, ticket_id):
        return self._tickets.get(ticket_id)

    async def get_ticket_by_id(self, ticket_id):
        return self._tickets.get(ticket_id)

    async def get_backlog_tickets(self, _project_id):
        return [ticket for ticket in self._tickets.values() if ticket.column == "Backlog"]

    async def get_tickets_by_column(self, _project_id, column):
        return [ticket for ticket in self._tickets.values() if ticket.column == column]

    async def create(self, ticket):
        if not ticket.id:
            ticket.id = f"created-{len(self._tickets) + 1}"
        self._tickets[ticket.id] = ticket
        return ticket

    async def update(self, ticket_or_id, updates=None):
        if updates is None:
            self._tickets[ticket_or_id.id] = ticket_or_id
            return ticket_or_id
        ticket = self._tickets[ticket_or_id]
        for key, value in updates.items():
            setattr(ticket, key, value)
        self._tickets[ticket.id] = ticket
        return ticket


class FakeGitService:
    def __init__(self):
        self.initialized = False

    def repo_exists(self, _project_id):
        return True

    async def initialize_repo(self, _project_id, _project_name):
        self.initialized = True
        return {"status": "initialized"}

    async def create_branch(self, _project_id, branch_name):
        return {"branch_name": branch_name, "status": "created"}

    async def commit_files(self, _project_id, files, commit_message):
        return {
            "commit_sha": "abc12345",
            "files": list(files.keys()),
            "message": commit_message,
            "branch": "ticket/test",
            "status": "committed",
        }

    async def checkout_branch(self, _project_id, _branch_name):
        return None

    async def get_branch_status(self, _project_id, branch_name=None):
        return {
            "branch": branch_name or "ticket/test",
            "commits": [
                {
                    "sha": "abc1234",
                    "message": "Test commit",
                    "files_changed": ["app.py", "tests/test_app.py"],
                }
            ],
        }


class FakeTestService:
    async def run_tests(self, _request):
        return {
            "status": "success",
            "passed": 3,
            "failed": 0,
            "errors": 0,
            "skipped": 0,
            "total": 3,
            "pass_rate": 1.0,
            "output": "3 passed",
            "duration": 0.25,
        }


class FakeEscalationManager:
    def get_current_tier(self, _ticket, _agent_name):
        return ETier.STANDARD

    async def record_success(self, ticket, _agent_name):
        if hasattr(ticket, "developer_failure_count"):
            ticket.developer_failure_count = 0
        if hasattr(ticket, "tester_failure_count"):
            ticket.tester_failure_count = 0
        return ticket

    async def record_failure(self, ticket, agent_name, _reason):
        if agent_name == "Developer":
            ticket.developer_failure_count += 1
            ticket.developer_llm_tier = ETier.STANDARD.value
        else:
            ticket.tester_failure_count += 1
            ticket.tester_llm_tier = ETier.STANDARD.value
        return ticket, ETier.STANDARD


class FakeSpecRepo:
    def __init__(self, documents):
        self._documents = documents
        self.updated = []

    async def find(self, _request):
        return self._documents

    async def update(self, request):
        self.updated.append(request)


def make_execution(agent, intent_name, response="response text", entities=None, message="user input"):
    return BehaviorExecution(
        agent=agent,
        message=message,
        intent=LlmIntent(
            response=response,
            intent=intent_name,
            agents_routing=[],
            entities=entities or {},
        ),
    )


def clone_ticket(sample_ticket, **overrides):
    ticket = copy.deepcopy(sample_ticket)
    for key, value in overrides.items():
        setattr(ticket, key, value)
    return ticket


@pytest.mark.asyncio
async def test_pm_behaviors_execute_with_fakes(sample_session, monkeypatch):
    request_session = FakeRequestSession()
    agent = SimpleNamespace(
        name="PM",
        session=sample_session,
        request=SimpleNamespace(session=request_session),
        log=lambda _message: None,
    )

    async def fake_log(_message):
        return None

    agent.log = fake_log

    result = await PmBasicReplyBehavior().run(make_execution(agent, "basic_reply", response="Hello"))
    assert result[0].content == "Hello"

    async def fake_create_project(self, name):
        return SimpleNamespace(id="project-1", name=name)

    monkeypatch.setattr("core.agents.behaviors.pm.create_project_behavior.ProjectsController.create_project", fake_create_project)
    result = await CreateProjectBehavior().run(make_execution(agent, "create_project", entities={"project_name": "Quarantine"}))
    assert "Quarantine" in result[0].content
    assert request_session["pending_action"]["project_id"] == "project-1"

    request_session["pending_action"] = {
        "type": "activate_project",
        "project_id": "project-1",
        "project_name": "Quarantine",
    }
    result = await ConfirmActionBehavior().run(make_execution(agent, "confirm_action", entities={"confirmation": "yes"}))
    assert "active project" in result[0].content
    assert request_session["project_id"] == "project-1"
    assert request_session.save_called is True

    delegated = []
    behavior = DelegateToSpecBuilderBehavior()

    async def fake_run_spec_builder(session, user_input):
        delegated.append((session.project_id, user_input))

    def fake_create_task(coro):
        coro.close()
        return None

    monkeypatch.setattr(behavior, "_run_spec_builder", fake_run_spec_builder)
    monkeypatch.setattr("core.agents.behaviors.pm.delegate_to_spec_builder_behavior.asyncio.create_task", fake_create_task)
    result = await behavior.run(make_execution(agent, "start_spec", message="start the spec"))
    assert "Specification Builder" in result[0].content

    async def fake_get_ticket_stats(self, _project_id):
        return {"open": 2, "done": 1}

    monkeypatch.setattr("core.agents.behaviors.pm.get_status_behavior.ProjectsService.get_ticket_stats", fake_get_ticket_stats)
    status_message = await GetStatusBehavior().run(make_execution(agent, "status"))
    assert "Open tickets: 2" in status_message.text

    fake_project = SimpleNamespace(paused=False)

    async def fake_get_project(self, _project_id):
        return fake_project

    async def fake_update_project(self, project):
        fake_project.paused = project.paused
        return project

    monkeypatch.setattr("core.agents.behaviors.pm.pause_project_behavior.ProjectsService.get_project_by_id", fake_get_project)
    monkeypatch.setattr("core.agents.behaviors.pm.pause_project_behavior.ProjectsService.update_project", fake_update_project)
    pause_message = await PauseProjectBehavior().run(make_execution(agent, "pause_project"))
    assert fake_project.paused is True
    assert "paused" in pause_message.text.lower()

    monkeypatch.setattr("core.agents.behaviors.pm.resume_project_behavior.ProjectsService.get_project_by_id", fake_get_project)
    monkeypatch.setattr("core.agents.behaviors.pm.resume_project_behavior.ProjectsService.update_project", fake_update_project)
    resume_message = await ResumeProjectBehavior().run(make_execution(agent, "resume_project"))
    assert fake_project.paused is False
    assert "resumed" in resume_message.text.lower()

    async def fake_rename(self, _project_id, new_name):
        return SimpleNamespace(name=new_name)

    monkeypatch.setattr("core.agents.behaviors.pm.rename_project_behavior.ProjectsService.rename_project", fake_rename)
    rename_message = await RenameProjectBehavior().run(make_execution(agent, "rename_project", entities={"projectName": "Renamed"}))
    assert "Renamed" in rename_message.text


@pytest.mark.asyncio
async def test_spec_behaviors_execute_with_fakes(sample_session, sample_spec_document, monkeypatch):
    spec_repo = FakeSpecRepo([sample_spec_document])
    agent = SimpleNamespace(name="Spec", session=sample_session, spec_repo=spec_repo)

    assert "response text" in (await StartSpecBehavior().run(make_execution(agent, "start_spec")))[0].content
    assert "response text" in (await AddToSpecBehavior().run(make_execution(agent, "add_to_spec")))[0].content
    assert "response text" in (await AskAQuestionBehavior().run(make_execution(agent, "ask_a_question")))[0].content
    assert "response text" in (await ChangeSpecBehavior().run(make_execution(agent, "change_spec")))[0].content

    behavior = FinalizeSpecBehavior()

    async def fake_run_architect(_session):
        return None

    def fake_create_task(coro):
        coro.close()
        return None

    monkeypatch.setattr(behavior, "_run_architect", fake_run_architect)
    monkeypatch.setattr("core.agents.behaviors.spec.finalize_spec_behavior.asyncio.create_task", fake_create_task)
    result = await behavior.run(make_execution(agent, "finalize_spec"))
    assert "finalized and approved" in result[0].content
    assert spec_repo.updated


@pytest.mark.asyncio
async def test_architect_behaviors_execute_with_fakes(sample_session, sample_spec_document, monkeypatch):
    ticket_repo = FakeTicketRepo([])
    spec_repo = FakeSpecRepo([sample_spec_document])
    agent = SimpleNamespace(name="Architect", session=sample_session, ticket_repo=ticket_repo, spec_repo=spec_repo)

    result = await ArchitectBasicReplyBehavior().run(make_execution(agent, "basic_reply", response="Architect ready"))
    assert "Architect ready" in result[0].content

    async def fake_response(self):
        return json.dumps([
            {
                "title": "Generated ticket",
                "description": "desc",
                "severity": "High",
                "label": "Feature",
                "eta": "1 week",
                "estimated_days": 7,
            }
        ])

    monkeypatch.setattr("core.agents.helpers.llm_exchange.LlmExchange.get_response", fake_response)
    result = await AnalyzeSpecBehavior().run(make_execution(agent, "analyze_spec"))
    assert "created 1 tickets" in result[0].content

    result = await RefineTicketsBehavior().run(make_execution(agent, "refine_tickets"))
    assert "found 1 existing tickets" in result[0].content


@pytest.mark.asyncio
async def test_developer_behaviors_execute_with_fakes(sample_ticket, monkeypatch):
    active_ticket = clone_ticket(sample_ticket, id="active-ticket", column="In Progress", agents=["Developer"], branch_name="ticket/test", test_files=["tests/test_app.py"])
    backlog_ticket = clone_ticket(sample_ticket, id="backlog-ticket", column="Backlog", agents=[], branch_name=None, test_files=[])
    todo_ticket = clone_ticket(sample_ticket, id="todo-ticket", column="To Do", agents=["Developer"], branch_name=None, test_files=[])
    ticket_repo = FakeTicketRepo([active_ticket, backlog_ticket, todo_ticket])
    session = SimpleNamespace(project_id="test_project_456", current_ticket=None, pending_code={})
    agent = SimpleNamespace(
        name="Developer",
        session=session,
        project=SimpleNamespace(id="test_project_456", title="Test Project"),
        ticket_repo=ticket_repo,
        git_service=FakeGitService(),
        escalation_manager=FakeEscalationManager(),
    )

    result = await DeveloperBasicReplyBehavior().run(make_execution(agent, "basic_reply"))
    assert "Developer Agent" in result[0].content

    result = await ClaimTicketBehavior().run(make_execution(agent, "claim_ticket", entities={"ticketId": backlog_ticket.id}))
    assert "Successfully claimed ticket" in result[0].content

    result = await CreateBranchBehavior().run(make_execution(agent, "create_branch", entities={"ticketId": todo_ticket.id}))
    assert "Git branch created successfully" in result[0].content

    async def fake_response(self):
        if "Analyze this development ticket" in self.request.content:
            return "analysis"
        return "FILE: app.py\n```python\ndef run():\n    return True\n```\nEXPLANATION: minimal"

    monkeypatch.setattr("core.agents.helpers.llm_exchange.LlmExchange.get_response", fake_response)
    result = await AnalyzeTicketBehavior().run(make_execution(agent, "analyze_ticket", entities={"ticketId": active_ticket.id}))
    assert "Ticket Analysis" in result[0].content

    result = await GenerateCodeBehavior().run(make_execution(agent, "generate_code", entities={"ticketId": active_ticket.id}))
    assert "Code generated successfully" in result[0].content
    assert agent.session.pending_code["app.py"].startswith("def run")

    result = await CommitCodeBehavior().run(make_execution(agent, "commit_code", entities={"ticketId": active_ticket.id, "commitMessage": "Implement feature"}))
    assert "Code committed successfully" in result[0].content
    assert agent.session.pending_code == {}

    active_ticket.commits = ["abc12345"]
    result = await RequestReviewBehavior().run(make_execution(agent, "request_review", entities={"ticketId": active_ticket.id}))
    assert "Code review requested" in result[0].content


@pytest.mark.asyncio
async def test_tester_behaviors_execute_with_fakes(sample_ticket, monkeypatch):
    review_ticket = clone_ticket(
        sample_ticket,
        column="Review",
        agents=["Developer"],
        branch_name="ticket/test",
        commits=["abc12345"],
        test_files=["tests/test_app.py"],
        test_results={"status": "success", "passed": 3, "failed": 0, "errors": 0, "total": 3, "duration": 0.25, "output": "3 passed"},
        test_pass_rate=1.0,
        developer_failure_count=0,
        developer_llm_tier="standard",
        tester_failure_count=0,
        tester_llm_tier="standard",
    )
    ticket_repo = FakeTicketRepo([review_ticket])
    session = SimpleNamespace(project_id="test_project_456", current_ticket=review_ticket.id, pending_tests={})
    agent = SimpleNamespace(
        name="Tester",
        session=session,
        project=SimpleNamespace(id="test_project_456"),
        ticket_repo=ticket_repo,
        git_service=FakeGitService(),
        test_service=FakeTestService(),
        escalation_manager=FakeEscalationManager(),
    )

    result = await TesterBasicReplyBehavior().run(make_execution(agent, "basic_reply"))
    assert "Tester Agent Status" in result[0].content

    result = await ClaimReviewTicketBehavior().run(make_execution(agent, "claim_review", entities={"ticketId": review_ticket.id}))
    assert "Claimed Ticket for Review" in result[0].content

    async def fake_response(self):
        content = self.request.content
        if "Analyze this code change for testing" in content:
            return "test analysis"
        return "```python\ndef test_feature():\n    assert False\n```"

    monkeypatch.setattr("core.agents.helpers.llm_exchange.LlmExchange.get_response", fake_response)
    result = await AnalyzeCodeBehavior().run(make_execution(agent, "analyze_code"))
    assert "Code Analysis Complete" in result[0].content

    result = await GenerateTestBehavior().run(make_execution(agent, "generate_test"))
    assert "Test Generated" in result[0].content
    assert agent.session.pending_tests

    result = await CommitTestBehavior().run(make_execution(agent, "commit_test"))
    assert "Tests Committed" in result[0].content
    assert agent.session.pending_tests == {}

    result = await ExecuteTestsBehavior().run(make_execution(agent, "execute_tests"))
    assert "Test Execution Complete" in result[0].content

    result = await VerifyPassBehavior().run(make_execution(agent, "verify_pass"))
    assert "GREEN Phase Complete" in result[0].content

    result = await ApproveCodeBehavior().run(make_execution(agent, "approve_code"))
    assert "Code Approved" in result[0].content

    review_ticket.column = "Review"
    review_ticket.agents = ["Developer", "Tester"]
    review_ticket.test_results = {"status": "failure", "passed": 1, "failed": 2, "errors": 0, "total": 3, "duration": 0.25, "output": "failed output"}
    review_ticket.test_pass_rate = 1 / 3
    session.current_ticket = review_ticket.id
    result = await RejectCodeBehavior().run(make_execution(agent, "reject_code", message="reject because tests failed"))
    assert "Code Rejected" in result[0].content


def encode_session_key(agent_name: str, project_id: str = "project-1") -> str:
    payload = json.dumps({"agent_name": agent_name, "project_id": project_id}).encode("utf-8")
    encoded = urlsafe_b64encode(payload).decode("utf-8").rstrip("=")
    return f"{encoded}:salt:signature"


def test_agent_generator_routes_only_reachable_chat_agents():
    generator = AgentGenerator()

    assert generator.get_agent(encode_session_key("PM")).name == "PM"
    assert generator.get_agent(encode_session_key("Spec")).name == "Spec"
    assert generator.get_agent(encode_session_key("Architect")).name == "Architect"
    assert generator.get_agent(encode_session_key("Developer")).name == "Developer"
    assert generator.get_agent(encode_session_key("Tester")).name == "Tester"
    assert generator.get_agent(encode_session_key("RD")) is None
