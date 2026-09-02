from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from core.dataclasses.ticket_model import TicketModel


class EscalationAgent(str, Enum):
    DEVELOPER = "Developer"
    TESTER = "Tester"


@dataclass(frozen=True)
class BranchCreateRequest:
    project_id: str
    branch_name: str
    base_branch: str = "main"


@dataclass(frozen=True)
class CommitFilesRequest:
    project_id: str
    files: dict[str, str]
    commit_message: str


@dataclass(frozen=True)
class FileContentRequest:
    project_id: str
    file_path: str
    branch_name: str | None = None


@dataclass(frozen=True)
class TestRunRequest:
    __test__ = False
    project_id: str
    test_files: list[str] | None = None
    verbose: bool = True


@dataclass(frozen=True)
class ChatMessageRequest:
    request: object
    session_key: str
    user_input: str


@dataclass(frozen=True)
class FailureRecordRequest:
    ticket: TicketModel
    agent_type: EscalationAgent
    reason: str
