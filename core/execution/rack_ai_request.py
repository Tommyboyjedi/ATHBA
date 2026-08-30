"""Typed ATHBA request boundary for Rack AI change execution."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any

from core.development.work_unit import DevelopmentWorkUnit


@dataclass(frozen=True)
class RepositoryBinding:
    repository_id: str
    base_ref: str
    base_sha: str | None = None
    registered_root: str | None = None
    environment_resources: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        _require_text(self.repository_id, "repository id")
        _require_text(self.base_ref, "base ref")
        if self.base_sha is not None:
            _require_text(self.base_sha, "base sha")
        if self.registered_root is not None:
            _require_text(self.registered_root, "registered root")
        for resource in self.environment_resources:
            _require_text(resource, "environment resource")

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "repository_id": self.repository_id,
            "base_ref": self.base_ref,
            "base_sha": self.base_sha,
            "registered_root": self.registered_root,
        }
        if self.environment_resources:
            payload["environment_resources"] = list(self.environment_resources)
        return payload

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "RepositoryBinding":
        return cls(
            repository_id=str(payload["repository_id"]),
            base_ref=str(payload["base_ref"]),
            base_sha=_optional_text(payload.get("base_sha")),
            registered_root=_optional_text(payload.get("registered_root")),
            environment_resources=_resource_list(payload.get("environment_resources")),
        )

    def with_base_sha(self, base_sha: str | None) -> "RepositoryBinding":
        if base_sha is None:
            return replace(self, base_sha=None)
        _require_text(base_sha, "base sha")
        return replace(self, base_sha=base_sha)


@dataclass(frozen=True)
class RackAiRepositoryTarget:
    repository_id: str
    base_ref: str
    base_sha: str | None = None
    root: str | None = None

    def to_dict(self) -> dict[str, str]:
        payload = {"id": self.repository_id, "base_ref": self.base_ref}
        if self.base_sha is not None:
            payload["base_sha"] = self.base_sha
        if self.root is not None:
            payload["root"] = self.root
        return payload


@dataclass(frozen=True)
class RackAiAcceptanceSpec:
    commands: list[list[str]]
    required_artifacts: list[str]

    def to_dict(self) -> dict[str, object]:
        return {
            "commands": [list(command) for command in self.commands],
            "required_artifacts": list(self.required_artifacts),
        }


@dataclass(frozen=True)
class RackAiExecutionLimits:
    max_implementation_attempts: int
    timeout_seconds: int
    network: str

    def to_dict(self) -> dict[str, object]:
        return {
            "max_implementation_attempts": self.max_implementation_attempts,
            "timeout_seconds": self.timeout_seconds,
            "network": self.network,
        }


@dataclass(frozen=True)
class RackAiChangeRequest:
    change_id: str
    repository: RackAiRepositoryTarget
    task: str
    allowed_paths: list[str]
    acceptance: RackAiAcceptanceSpec
    limits: RackAiExecutionLimits
    environment_resources: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "change_id": self.change_id,
            "repository": self.repository.to_dict(),
            "task": self.task,
            "allowed_paths": list(self.allowed_paths),
            "acceptance": self.acceptance.to_dict(),
            "limits": self.limits.to_dict(),
        }
        if self.environment_resources:
            payload["environment_resources"] = list(self.environment_resources)
        return payload


@dataclass(frozen=True)
class RackAiRequestBuildRequest:
    workload_id: str
    binding: RepositoryBinding
    unit: DevelopmentWorkUnit


class RackAiRequestFactory:
    def build(self, request: RackAiRequestBuildRequest) -> RackAiChangeRequest:
        _require_text(request.workload_id, "workload id")
        if not request.unit.is_ready_for_execution():
            raise ValueError("work unit must be marked ready for execution before Rack AI submission")
        return RackAiChangeRequest(
            change_id=f"{request.workload_id}--{request.unit.id}",
            repository=RackAiRepositoryTarget(
                repository_id=request.binding.repository_id,
                base_ref=request.binding.base_ref,
                base_sha=request.binding.base_sha,
                root=request.binding.registered_root,
            ),
            task=request.unit.objective,
            allowed_paths=list(request.unit.allowed_paths),
            acceptance=RackAiAcceptanceSpec(
                commands=[list(command) for command in request.unit.acceptance.commands],
                required_artifacts=list(request.unit.acceptance.required_artifacts),
            ),
            limits=RackAiExecutionLimits(
                max_implementation_attempts=request.unit.max_implementation_attempts,
                timeout_seconds=request.unit.timeout_seconds,
                network=request.unit.network,
            ),
            environment_resources=list(request.binding.environment_resources),
        )


def to_rack_ai_request(workload_id: str, binding: RepositoryBinding, unit: DevelopmentWorkUnit) -> dict[str, Any]:
    return RackAiRequestFactory().build(RackAiRequestBuildRequest(workload_id, binding, unit)).to_dict()


def _optional_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value)
    if not text.strip():
        raise ValueError("optional text values must be non-empty when present")
    return text


def _resource_list(value: Any) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError("environment resources must be a list when present")
    resources = [str(item) for item in value]
    for resource in resources:
        _require_text(resource, "environment resource")
    return resources


def _require_text(value: str, label: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be non-empty")
