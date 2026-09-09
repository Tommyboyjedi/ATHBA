"""Read-only canonical Git inspection. Never import or execute project code."""
from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from core.development.specification_evidence_policy import RevisionFile, SpecificationSnapshot

GIT_READ_TIMEOUT = 10


@dataclass(frozen=True)
class GitSpecificationSnapshot:
    repository_root: Path

    def read(self, revision: str) -> SpecificationSnapshot:
        try:
            canonical = self._git(("rev-parse", "--verify", f"{revision}^{{commit}}" )).strip()
            entries = self._git(("ls-tree", "-rz", canonical)).split("\0")
            files = []
            for entry in filter(None, entries):
                metadata, path = entry.split("\t", 1)
                if metadata.split()[0] != "100644" and metadata.split()[0] != "100755":
                    return SpecificationSnapshot(canonical, (), False, (f"unsupported Git entry: {path}",))
                files.append(RevisionFile(path, self._git(("show", f"{canonical}:{path}"))))
            return SpecificationSnapshot(canonical, tuple(files))
        except (subprocess.SubprocessError, UnicodeError, ValueError, OSError) as error:
            return SpecificationSnapshot(revision, (), False, (f"snapshot unavailable: {type(error).__name__}",))

    def _git(self, args: tuple[str, ...]) -> str:
        return subprocess.run(["git", *args], cwd=self.repository_root, check=True,
                              capture_output=True, text=True, timeout=GIT_READ_TIMEOUT).stdout


def production_python(file: RevisionFile) -> bool:
    path = PurePosixPath(file.path)
    return path.suffix == ".py" and not (
        set(path.parts) & {"tests", "test", ".venv", "venv"}
        or path.name.startswith("test_") or path.name in {"conftest.py", "setup.py"}
    )
