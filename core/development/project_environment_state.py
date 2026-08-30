"""ATHBA-owned project runtime and lifecycle state."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class ProjectLifecycleState(str, Enum):
    CREATED = "created"
    PREPARED = "prepared"
    READY = "ready"
    RETIRED = "retired"


class EnvironmentLifetime(str, Enum):
    SHARED = "shared"
    PROJECT_PERSISTENT = "project_persistent"
    DISPOSABLE = "disposable"


@dataclass(frozen=True)
class EnvironmentResource:
    path: str

    def __post_init__(self) -> None:
        _require_text(self.path, "environment resource")

    def to_dict(self) -> str:
        return self.path

    @classmethod
    def from_dict(cls, payload: object) -> "EnvironmentResource":
        return cls(path=str(payload))


@dataclass(frozen=True)
class ProjectRuntime:
    kind: str
    version: str
    environment_path: str
    test_command: list[str]
    build_command: list[str] | None = None
    lifetime: str = EnvironmentLifetime.SHARED.value
    environment_resources: list[EnvironmentResource] = field(default_factory=list)

    def __post_init__(self) -> None:
        _require_text(self.kind, "runtime kind")
        _require_text(self.version, "runtime version")
        _require_text(self.environment_path, "runtime environment path")
        object.__setattr__(self, "lifetime", _enum_value(self.lifetime, EnvironmentLifetime, "runtime lifetime"))
        _validate_command(self.test_command, "test command")
        if self.build_command is not None:
            _validate_command(self.build_command, "build command")

    def resource_paths(self) -> list[str]:
        return [resource.path for resource in self.environment_resources]

    def to_dict(self) -> dict[str, object]:
        return {
            "kind": self.kind,
            "version": self.version,
            "environment_path": self.environment_path,
            "test_command": list(self.test_command),
            "build_command": None if self.build_command is None else list(self.build_command),
            "lifetime": self.lifetime,
            "environment_resources": [resource.to_dict() for resource in self.environment_resources],
        }

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> "ProjectRuntime":
        return cls(
            kind=str(data["kind"]),
            version=str(data["version"]),
            environment_path=str(data["environment_path"]),
            test_command=[str(value) for value in data["test_command"]],
            build_command=None if data.get("build_command") is None else [str(value) for value in data["build_command"]],
            lifetime=str(data.get("lifetime", EnvironmentLifetime.SHARED.value)),
            environment_resources=[
                EnvironmentResource.from_dict(value)
                for value in data.get("environment_resources", [])
            ],
        )


@dataclass(frozen=True)
class DevelopmentProject:
    project_id: str
    repository_root: str
    default_ref: str
    trusted_base_sha: str
    runtime: ProjectRuntime
    generated_paths: list[str]
    status: str
    workspace_lifetime: str = EnvironmentLifetime.PROJECT_PERSISTENT.value

    def __post_init__(self) -> None:
        _require_text(self.project_id, "project id")
        _require_text(self.repository_root, "repository root")
        _require_text(self.default_ref, "default ref")
        _require_text(self.trusted_base_sha, "trusted base sha")
        object.__setattr__(self, "status", _enum_value(self.status, ProjectLifecycleState, "project status"))
        object.__setattr__(self, "workspace_lifetime", _enum_value(self.workspace_lifetime, EnvironmentLifetime, "workspace lifetime"))
        _validate_paths(self.generated_paths, "generated paths")

    def binding(self):
        from core.execution.rack_ai_request import RepositoryBinding

        return RepositoryBinding(
            repository_id=self.project_id,
            base_ref=self.default_ref,
            base_sha=self.trusted_base_sha,
            registered_root=self.repository_root,
            environment_resources=self.runtime.resource_paths(),
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "project_id": self.project_id,
            "repository_root": self.repository_root,
            "default_ref": self.default_ref,
            "trusted_base_sha": self.trusted_base_sha,
            "runtime": self.runtime.to_dict(),
            "generated_paths": list(self.generated_paths),
            "status": self.status,
            "workspace_lifetime": self.workspace_lifetime,
        }

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> "DevelopmentProject":
        return cls(
            project_id=str(data["project_id"]),
            repository_root=str(data["repository_root"]),
            default_ref=str(data["default_ref"]),
            trusted_base_sha=str(data["trusted_base_sha"]),
            runtime=ProjectRuntime.from_dict(dict(data["runtime"])),
            generated_paths=[str(value) for value in data.get("generated_paths", [])],
            status=str(data["status"]),
            workspace_lifetime=str(data.get("workspace_lifetime", EnvironmentLifetime.PROJECT_PERSISTENT.value)),
        )


def _enum_value(value: str, enum_type: type[Enum], label: str) -> str:
    text = str(value)
    try:
        return enum_type(text).value
    except ValueError as error:
        raise ValueError(f"invalid {label}: {text}") from error


def _validate_command(command: list[str], label: str) -> None:
    if not command:
        raise ValueError(f"{label} must not be empty")
    if any(not isinstance(value, str) or not value.strip() for value in command):
        raise ValueError(f"{label} must contain non-empty strings")


def _validate_paths(values: list[str], label: str) -> None:
    if any(not isinstance(value, str) or not value.strip() for value in values):
        raise ValueError(f"{label} must contain non-empty paths")


def _require_text(value: str, label: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be non-empty")
