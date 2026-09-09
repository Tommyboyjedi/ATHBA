"""Direct-argv Git capability for microcycle revision lifecycle effects."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path


ZERO_OBJECT_ID = "0" * 40


@dataclass(frozen=True)
class RevisionResolveRequest:
    ref: str


@dataclass(frozen=True)
class RevisionAncestryRequest:
    ancestor: str
    descendant: str


@dataclass(frozen=True)
class RevisionUpdateRequest:
    ref: str
    target: str
    expected_current: str


@dataclass(frozen=True)
class RevisionDeleteRequest:
    ref: str
    expected_current: str


class MicrocycleGitClient:
    """Resolves and atomically mutates refs for one owned repository."""

    def __init__(self, repository_root: str | Path):
        self.repository_root = Path(repository_root).resolve()

    def resolve(self, request: RevisionResolveRequest) -> str | None:
        result = self._run("rev-parse", "--verify", f"{request.ref}^{{commit}}", check=False)
        return result.stdout.strip() if result.returncode == 0 else None

    def commit_exists(self, request: RevisionResolveRequest) -> bool:
        return self.resolve(request) is not None

    def is_ancestor(self, request: RevisionAncestryRequest) -> bool:
        return self._run(
            "merge-base", "--is-ancestor", request.ancestor, request.descendant, check=False
        ).returncode == 0

    def update(self, request: RevisionUpdateRequest) -> None:
        self._run("update-ref", request.ref, request.target, request.expected_current)

    def delete(self, request: RevisionDeleteRequest) -> None:
        self._run("update-ref", "-d", request.ref, request.expected_current)

    def _run(self, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
        result = subprocess.run(
            ["git", *args], cwd=self.repository_root, capture_output=True, text=True, check=False
        )
        if check and result.returncode:
            raise subprocess.CalledProcessError(result.returncode, ["git", *args], result.stdout, result.stderr)
        return result