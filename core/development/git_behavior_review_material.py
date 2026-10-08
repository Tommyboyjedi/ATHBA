"""Read the selected production path at immutable ATHBA-owned Git revisions."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePosixPath
import re
import subprocess

from core.development.behavior_review_material import BehaviorProductionMaterial, BehaviorProductionReadRequest


@dataclass(frozen=True)
class GitBehaviorProductionReader:
    def read(self, request: BehaviorProductionReadRequest) -> BehaviorProductionMaterial:
        path = PurePosixPath(request.production_path)
        if path.is_absolute() or ".." in path.parts or not path.parts or "\\" in request.production_path:
            raise ValueError("behavior review requires an exact relative production path")
        if any(re.fullmatch(r"(?:[a-f0-9]{40}|[a-f0-9]{64})", revision) is None
               for revision in (request.entry_revision, request.revision)):
            raise ValueError("behavior review requires immutable revision identities")
        source = _git(request, ("show", f"{request.revision}:{request.production_path}"))
        diff = _git(request, ("diff", request.entry_revision, request.revision, "--", request.production_path))
        return BehaviorProductionMaterial(request.production_path, source, diff, request.entry_revision, request.revision)


def _git(request: BehaviorProductionReadRequest, arguments: tuple[str, ...]) -> str:
    result = subprocess.run(("git", "--literal-pathspecs", *arguments), cwd=request.repository_root,
                            text=True, capture_output=True, check=False)
    if result.returncode:
        raise ValueError("immutable behavior production material unavailable")
    return result.stdout
