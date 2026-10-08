"""Bounded current-revision material for independent behavior review."""
from __future__ import annotations

from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Protocol


@dataclass(frozen=True)
class BehaviorProductionMaterial:
    path: str
    source: str
    diff: str
    entry_revision: str
    revision: str

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


@dataclass(frozen=True)
class BehaviorProductionReadRequest:
    repository_root: Path
    production_path: str
    entry_revision: str
    revision: str


class BehaviorProductionReader(Protocol):
    def read(self, request: BehaviorProductionReadRequest) -> BehaviorProductionMaterial: ...
