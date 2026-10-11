"""Language capabilities used by orchestration; no concrete syntax or runner defaults."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class TestModuleMergeRequest:
    trusted_source: str
    scenario_source: str
    canonical_test_identity: str


@dataclass(frozen=True)
class TestSourceRequest:
    source: str
    identity: str


class TestMaterialAdapter(Protocol):
    adapter_id: str
    language_id: str
    framework: str

    def merge(self, request: TestModuleMergeRequest) -> str: ...
    def extract(self, request: TestSourceRequest) -> str | None: ...
    def test_path(self, identity: str) -> str: ...
    def acceptance_command(self, identity: str) -> list[str]: ...
    def syntax_command(self, path: str) -> list[str]: ...


def require_test_material(adapter: TestMaterialAdapter | None) -> TestMaterialAdapter:
    if adapter is None:
        raise ValueError("test material capability has not been configured")
    return adapter
