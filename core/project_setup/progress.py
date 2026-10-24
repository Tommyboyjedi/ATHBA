"""Exact setup-owned progress, never authority to adopt an unknown repository."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field, replace
import hashlib
import os
from pathlib import Path
import stat
from typing import Callable

from core.atomic_json_file import read_json_file, write_json_atomically
from core.project_setup.architecture import validate_scope


PROGRESS_FILE = "setup-progress.json"
PROGRESS_SCHEMA = "athba/setup-progress/v1"
DEFAULT_CANONICAL_REF = "refs/heads/main"
REGULAR_GIT_MODES = frozenset({"100644", "100755"})


@dataclass(frozen=True)
class SetupWork:
    project_id: str
    setup_identity: str
    architecture_sha256: str
    specification_sha256: str
    repository_root: str
    profile_sha256: str
    runtime_sha256: str
    expected_files: dict[str, str]
    test_paths: tuple[str, ...]


@dataclass(frozen=True)
class SetupProgress:
    work: SetupWork
    seed_revision: str | None = None
    canonical_ref: str = DEFAULT_CANONICAL_REF
    created: bool = True
    git_identity: tuple[int, int] | None = None
    references: dict[str, str] = field(default_factory=dict)
    files_written: bool = False
    scaffold_revision: str | None = None
    provenance: tuple[tuple[str, str], ...] = ()


class SetupProgressJournal:
    """Persist one exact setup identity under the existing project setup lock."""

    def __init__(self, project_root: Path):
        self.root = project_root

    def load(self) -> SetupProgress | None:
        path = self._path()
        if not path.exists():
            return None
        value = read_json_file(path)
        if value.pop("schema", None) != PROGRESS_SCHEMA:
            raise ValueError("unsupported setup progress schema")
        fields = {key: value.pop(key) for key in SetupWork.__dataclass_fields__}
        fields["test_paths"] = tuple(fields["test_paths"])
        if value.get("git_identity") is not None:
            value["git_identity"] = tuple(value["git_identity"])
        value["provenance"] = tuple(tuple(item) for item in value.get("provenance", ()))
        return SetupProgress(work=SetupWork(**fields), **value)

    def start(self, work: SetupWork) -> SetupProgress:
        current = self.load()
        if current is not None:
            if current.work != work:
                raise ValueError("setup progress authority differs from approved setup")
            return current
        record = SetupProgress(work)
        self.save(record)
        return record

    def save(self, record: SetupProgress) -> None:
        current = self.load()
        if current is not None:
            _require_same_authority(current, record)
        value = asdict(record)
        value.update(value.pop("work"))
        write_json_atomically(self._path(), {"schema": PROGRESS_SCHEMA, **value})

    def _path(self) -> Path:
        _confined_directory(self.root)
        path = self.root / PROGRESS_FILE
        if path.is_symlink() or (path.exists() and not path.is_file()):
            raise ValueError("setup progress must be an ordinary owned file")
        return path


class SetupProgressVerifier:
    """Verify only the exact seed, scaffold and file effects recorded by setup."""

    def __init__(self, run: Callable[..., str], generated_paths: tuple[str, ...] = ()):
        self.run = run
        self.generated_paths = generated_paths

    def snapshot(self, record: SetupProgress) -> SetupProgress:
        root = Path(record.work.repository_root)
        _repository_directory(root)
        item = (root / ".git").stat()
        bound = replace(record, git_identity=(item.st_dev, item.st_ino),
                        references=self._references(root))
        self.verify(bound)
        return bound

    def verify(self, record: SetupProgress) -> None:
        root = Path(record.work.repository_root)
        _confined_directory(root)
        if record.seed_revision is None:
            if root.exists():
                raise ValueError("setup initialization outcome has no recorded seed authority")
            return
        _repository_directory(root)
        item = (root / ".git").stat()
        if record.git_identity != (item.st_dev, item.st_ino):
            raise ValueError("setup Git directory identity changed")
        if Path(self.run(root, "rev-parse", "--show-toplevel").strip()) != root:
            raise ValueError("setup Git top level differs from its recorded root")
        common = Path(self.run(root, "rev-parse", "--git-common-dir").strip())
        if (root / common).resolve() != root / ".git":
            raise ValueError("setup Git common directory is outside its owned root")
        if self.run(root, "symbolic-ref", "HEAD").strip() != record.canonical_ref:
            raise ValueError("setup checkout changed its recorded canonical branch")
        actual = self._references(root)
        if set(actual) != set(record.references):
            raise ValueError("setup repository gained or lost references")
        permitted = {record.seed_revision, record.scaffold_revision}
        for name, revision in actual.items():
            if name == record.canonical_ref:
                if revision not in permitted:
                    raise ValueError("setup canonical revision advanced beyond recorded authority")
            elif revision != record.references[name]:
                raise ValueError("setup repository reference changed")
        if record.references.get(record.canonical_ref) != record.seed_revision:
            raise ValueError("setup seed reference snapshot is inconsistent")
        baseline = _tree(self.run(root, "ls-tree", "-r", "-z", record.seed_revision))
        authority = _FileAuthority(record, baseline, self.run, self.generated_paths)
        _verify_files(authority)
        _verify_index(authority)
        _verify_scaffold(authority)

    def _references(self, root: Path) -> dict[str, str]:
        output = self.run(root, "for-each-ref", "--format=%(refname) %(objectname)")
        return dict(line.split(" ", 1) for line in output.splitlines())


def _require_same_authority(current: SetupProgress, record: SetupProgress) -> None:
    if current.work != record.work:
        raise ValueError("setup progress authority differs from approved setup")
    fields = ("seed_revision", "canonical_ref", "created", "git_identity", "references")
    if current.seed_revision is not None and any(
            getattr(current, name) != getattr(record, name) for name in fields):
        raise ValueError("setup seed authority cannot be replaced")
    if current.files_written and not record.files_written:
        raise ValueError("setup progress cannot discard verified file effects")
    if current.scaffold_revision is not None and current.scaffold_revision != record.scaffold_revision:
        raise ValueError("setup scaffold authority cannot be replaced")
    if current.provenance and current.provenance != record.provenance:
        raise ValueError("setup recovery provenance cannot be replaced")


def _confined_directory(root: Path) -> None:
    if not root.is_absolute() or root != root.resolve():
        raise ValueError("setup progress paths must be absolute without symlink traversal")
    if root.exists() and not root.is_dir():
        raise ValueError("setup progress root is not a directory")


def _repository_directory(root: Path) -> None:
    _confined_directory(root)
    git = root / ".git"
    if not root.is_dir() or git.is_symlink() or not git.is_dir():
        raise ValueError("setup progress requires its original canonical Git directory")


def _tree(output: str) -> dict[str, tuple[str, str]]:
    result = {}
    for entry in output.split("\0"):
        if entry:
            metadata, path = entry.split("\t", 1)
            mode, kind, revision = metadata.split()
            if kind != "blob" or mode not in REGULAR_GIT_MODES:
                raise ValueError("setup baseline contains unsupported non-regular entries")
            result[path] = (mode, revision)
    return result


def _allowed_paths(record: SetupProgress, baseline: dict[str, tuple[str, str]]) -> set[str]:
    root = Path(record.work.repository_root)
    paths = set(baseline) | set(record.work.expected_files)
    for relative in paths | set(record.work.test_paths):
        candidate = Path(relative)
        if candidate.is_absolute() or relative != candidate.as_posix() or any(
                part in {"", ".", "..", ".git"} for part in relative.split("/")):
            raise ValueError("setup progress contains an unsafe relative path")
        if (root / candidate).resolve().is_relative_to(root) is False:
            raise ValueError("setup progress path escaped its owned root")
    return paths


@dataclass(frozen=True)
class _FileAuthority:
    record: SetupProgress
    baseline: dict[str, tuple[str, str]]
    run: Callable[..., str]
    generated_paths: tuple[str, ...] = ()


def _generated_paths(authority: _FileAuthority) -> tuple[Path, ...]:
    root = Path(authority.record.work.repository_root)
    protected = {Path(name) for name in _allowed_paths(authority.record, authority.baseline)
                 | set(authority.record.work.test_paths)}
    generated = []
    for name in authority.generated_paths:
        validate_scope(name)
        output = Path(name)
        if not (root / output).resolve().is_relative_to(root):
            raise ValueError("generated setup output escaped its owned root")
        if any(output == path or output in path.parents or path in output.parents for path in protected):
            raise ValueError("generated setup output overlaps protected source, scaffold, test or baseline")
        generated.append(output)
    return tuple(generated)


def _is_generated(relative: Path, generated: tuple[Path, ...]) -> bool:
    return ".git" not in relative.parts and any(
        relative == output or output in relative.parents for output in generated)


def _verify_files(authority: _FileAuthority) -> None:
    record, baseline, run = authority.record, authority.baseline, authority.run
    root = Path(record.work.repository_root)
    allowed = _allowed_paths(record, baseline)
    generated = _generated_paths(authority)
    directories = {str(parent) for name in allowed | set(record.work.test_paths) | {str(path) for path in generated}
                   for parent in Path(name).parents if str(parent) != "."}
    for parent, child_dirs, files in os.walk(root, followlinks=False):
        if Path(parent) == root:
            child_dirs[:] = [name for name in child_dirs if name != ".git"]
        for name in child_dirs:
            path = Path(parent) / name
            directory = path.relative_to(root)
            if path.is_symlink() or (directory.as_posix() not in directories and not _is_generated(directory, generated)):
                raise ValueError("setup contains an unrecorded directory or symlink")
        for name in files:
            path = Path(parent) / name
            relative = path.relative_to(root).as_posix()
            if not stat.S_ISREG(path.lstat().st_mode) or (
                    relative not in allowed and not _is_generated(Path(relative), generated)):
                raise ValueError("setup contains an unrecorded or non-regular file")
    for relative in allowed:
        path = root / relative
        if not path.exists():
            if relative in baseline or record.files_written:
                raise ValueError("setup lost a recorded scaffold file")
            continue
        executable = bool(path.stat().st_mode & (stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH))
        if executable != (baseline.get(relative, ("100644", ""))[0] == "100755"):
            raise ValueError("setup file mode differs from its recorded authority")
        expected = record.work.expected_files.get(relative)
        if expected is not None and hashlib.sha256(path.read_bytes()).hexdigest() == expected:
            continue
        if relative in baseline and (expected is None or (relative == ".gitignore" and not record.files_written)):
            if run(root, "hash-object", "--", relative).strip() == baseline[relative][1]:
                continue
        raise ValueError("setup file content differs from its recorded authority")


def _verify_index(authority: _FileAuthority) -> None:
    record, baseline, run = authority.record, authority.baseline, authority.run
    root = Path(record.work.repository_root)
    allowed = _allowed_paths(record, baseline)
    indexed: dict[str, tuple[str, str]] = {}
    for entry in run(root, "ls-files", "--stage", "-z").split("\0"):
        if not entry:
            continue
        metadata, relative = entry.split("\t", 1)
        mode, revision, stage = metadata.split()
        if stage != "0" or mode not in REGULAR_GIT_MODES or relative not in allowed:
            raise ValueError("setup index contains unapproved entries or conflicts")
        indexed[relative] = (mode, revision)
        if indexed[relative] == baseline.get(relative):
            continue
        path = root / relative
        if relative not in record.work.expected_files or not path.is_file():
            raise ValueError("setup index differs from its recorded baseline")
        if revision != run(root, "hash-object", "--", relative).strip():
            raise ValueError("setup index content differs from its approved file")
        if mode != (baseline.get(relative) or ("100644", ""))[0]:
            raise ValueError("setup index changed a recorded file mode")
    if not set(baseline).issubset(indexed):
        raise ValueError("setup index deleted a recorded baseline file")


def _verify_scaffold(authority: _FileAuthority) -> None:
    record, baseline, run = authority.record, authority.baseline, authority.run
    if record.scaffold_revision is None:
        return
    root = Path(record.work.repository_root)
    if record.scaffold_revision != record.seed_revision:
        ancestry = run(root, "rev-list", "--parents", "-n", "1", record.scaffold_revision).split()
        if ancestry != [record.scaffold_revision, record.seed_revision]:
            raise ValueError("setup scaffold is not the recorded seed successor")
    expected = dict(baseline)
    for relative in record.work.expected_files:
        expected[relative] = (baseline.get(relative, ("100644", ""))[0],
                              run(root, "hash-object", "--", relative).strip())
    if _tree(run(root, "ls-tree", "-r", "-z", record.scaffold_revision)) != expected:
        raise ValueError("setup scaffold tree differs from recorded file authority")
