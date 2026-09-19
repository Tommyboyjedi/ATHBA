from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from uuid import UUID


@dataclass(frozen=True)
class MongoUpdateRequest:
    filter: dict[str, Any]
    update: dict[str, Any]
    upsert: bool = False


@dataclass(frozen=True)
class MongoFindRequest:
    filter: dict[str, Any]
    sort: list[tuple[str, int]] = field(default_factory=list)
    limit: int = 0


@dataclass(frozen=True)
class SnippetSaveRequest:
    project_id: UUID
    snippet_id: UUID
    language: str
    code: str
    origin: str
    context: str


@dataclass(frozen=True)
class SpecVersionCreateRequest:
    project_id: str
    content: Any
    author: str
    diff: str | None = None


@dataclass(frozen=True)
class AgentLogEntry:
    project_id: str
    agent: str
    action: str
    details: dict[str, Any]


@dataclass(frozen=True)
class CodeFileSaveRequest:
    project_id: str
    filename: str
    code: str
