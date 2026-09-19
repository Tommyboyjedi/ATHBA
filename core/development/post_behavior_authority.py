"""Deterministic post-behavior write authority, independent of model acceptance."""
from __future__ import annotations

import ast
import keyword
from dataclasses import dataclass

from core.development.post_behavior_assessment import IdentifierRename
from core.development.post_behavior_rename import RenameSelection, exact_renamed_source, select_target
from core.development.post_behavior_slice import FocusedProductionSlice
from core.development.post_behavior_refactor import RefactorSourcePair, frozen_sources_match, public_surface
from core.development.specification_evidence_policy import RevisionFile, SpecificationSnapshot
from core.development.specification_revision_snapshot import production_python


@dataclass(frozen=True)
class WriteAuthorityResult:
    passed: bool
    reason: str


@dataclass(frozen=True)
class RenameAuthorityRequest:
    trusted: SpecificationSnapshot
    candidate: SpecificationSnapshot
    production: FocusedProductionSlice
    mapping: IdentifierRename


@dataclass(frozen=True)
class RefactorAuthorityRequest:
    trusted: SpecificationSnapshot
    candidate: SpecificationSnapshot
    production: FocusedProductionSlice


class PythonPostBehaviorAuthority:
    """Require mechanically exact renaming or focused production-only refactoring."""

    def rename(self, request: RenameAuthorityRequest) -> WriteAuthorityResult:
        problem = snapshot_problem(request)
        if problem:
            return WriteAuthorityResult(False, problem)
        mapping = request.mapping
        names = (mapping.current_name, mapping.required_name)
        if any(not name.isidentifier() or keyword.iskeyword(name) for name in names) or names[0] == names[1]:
            return WriteAuthorityResult(False, "rename requires distinct Python identifiers")
        try:
            selection = RenameSelection(request.trusted, request.production, *names)
            target = select_target(selection)
            before = {file.path: file for file in request.trusted.files}
            changed = False
            for file in request.candidate.files:
                original = before[file.path]
                expected = original.source
                if file.path.endswith(".py"):
                    expected = exact_renamed_source(original, target)
                if file.source != expected:
                    return WriteAuthorityResult(False, f"non-authorized rename edit: {file.path}")
                changed = changed or expected != original.source
            return WriteAuthorityResult(changed, "exact identifier references only" if changed else "rename made no change")
        except (SyntaxError, ValueError, TypeError, IndentationError) as error:
            return WriteAuthorityResult(False, f"rename authority unsupported: {error}")

    def refactor(self, request: RefactorAuthorityRequest) -> WriteAuthorityResult:
        problem = snapshot_problem(request)
        if problem:
            return WriteAuthorityResult(False, problem)
        before = {file.path: file for file in request.trusted.files}
        changed = False
        try:
            for file in request.candidate.files:
                original = before[file.path]
                if file == original:
                    continue
                changed = True
                if file.path not in request.production.scope.production_paths or not production_python(file):
                    return WriteAuthorityResult(False, f"refactoring cannot write: {file.path}")
                if public_surface(original.source) != public_surface(file.source):
                    return WriteAuthorityResult(False, f"public interface changed: {file.path}")
                if not frozen_sources_match(RefactorSourcePair(original, file, request.production)):
                    return WriteAuthorityResult(False, f"outside focused production slice: {file.path}")
            return WriteAuthorityResult(changed, "focused production-only change" if changed else "refactor made no change")
        except (SyntaxError, ValueError, TypeError, IndentationError) as error:
            return WriteAuthorityResult(False, f"refactor authority unsupported: {error}")


def snapshot_problem(request: RenameAuthorityRequest | RefactorAuthorityRequest) -> str:
    if not request.trusted.complete or not request.candidate.complete:
        return "write authority requires complete immutable snapshots"
    if request.trusted.revision != request.production.revision:
        return "focused production revision mismatch"
    before = [file.path for file in request.trusted.files]
    after = [file.path for file in request.candidate.files]
    if len(set(before)) != len(before) or len(set(after)) != len(after):
        return "duplicate snapshot paths"
    if set(before) != set(after):
        return "post-behavior file creation/deletion is unauthorized"
    if any(not path or path.startswith("/") or ".." in path.split("/") for path in before):
        return "unsafe snapshot path"
    return ""
