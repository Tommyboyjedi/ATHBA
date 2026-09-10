"""Deterministic specification evidence as a Python language capability."""
from __future__ import annotations

import ast
from dataclasses import dataclass, replace
from pathlib import PurePosixPath

from core.development.microcycle_domain import LanguageAdapterDescriptor
from core.development.python_specification_dependencies import dependency_findings
from core.development.python_specification_storage import DECORATOR_ASSURANCE, decorator_warnings, storage_findings
from core.development.python_specification_surface import capability_matches, inspect_surface, known_capability
from core.development.specification_evidence_policy import EvidenceDecision, EvidenceResult, EvidenceStatus, SpecificationSnapshot
from core.development.specification_obligations import EvidencePolicy, ObligationModality
from core.development.specification_revision_snapshot import production_python

FOREIGN_SOURCE_SUFFIXES = frozenset({".rs", ".js", ".ts", ".c", ".cpp", ".so", ".pyd", ".java", ".go", ".sh"})


@dataclass(frozen=True)
class PythonSpecificationEvidenceAdapter:
    descriptor = LanguageAdapterDescriptor("python-specification", "1", "python")

    def verify(self, decision: EvidenceDecision, snapshot: SpecificationSnapshot) -> EvidenceResult:
        try:
            trees = tuple(ast.parse(file.source) for file in snapshot.files if production_python(file))
        except SyntaxError:
            return unsupported(decision, snapshot, ("invalid Python source",))
        if not snapshot.complete or not trees or any(PurePosixPath(file.path).suffix in FOREIGN_SOURCE_SUFFIXES for file in snapshot.files):
            return unsupported(decision, snapshot, snapshot.diagnostics + ("incomplete/unsupported source boundary",))
        if decision.policy in {EvidencePolicy.NON_GOAL, EvidencePolicy.PUBLIC_SURFACE}:
            return surface_result(decision, snapshot, trees)
        warnings: tuple[str, ...] = ()
        if decision.policy == EvidencePolicy.DEPENDENCY:
            failed, unknown = dependency_findings(snapshot)
        elif decision.policy == EvidencePolicy.STORAGE:
            if decision.modality != ObligationModality.FORBIDDEN and "in-memory" not in decision.subject and "in memory" not in decision.subject:
                return unsupported(decision, snapshot, ("positive persistence has no static absence policy",))
            failed, unknown = storage_findings(trees)
            warnings = decorator_warnings(trees, tuple(file.path for file in snapshot.files if production_python(file)))
            dependencies, metadata_unknown = dependency_findings(snapshot)
            unknown += metadata_unknown + dependencies
            unknown += tuple(f"{file.path}: unsupported persistence configuration" for file in snapshot.files
                             if PurePosixPath(file.path).suffix in {".json", ".yaml", ".yml", ".ini", ".cfg"}
                             and PurePosixPath(file.path).name not in {"pytest.ini", "tox.ini", "setup.cfg"})
        elif decision.policy == EvidencePolicy.QUALITY:
            return quality_result(decision, snapshot, trees)
        else:
            return unsupported(decision, snapshot, ("no deterministic verifier registered",))
        if failed:
            return EvidenceResult(EvidenceStatus.FAIL, decision.policy, snapshot.revision, failed, warnings)
        if unknown:
            return replace(unsupported(decision, snapshot, unknown), findings=warnings)
        details = (DECORATOR_ASSURANCE,) if warnings else ("canonical source and declarations satisfy the bounded static policy",)
        return EvidenceResult(EvidenceStatus.PASS, decision.policy, snapshot.revision, details, warnings)


def unsupported(decision: EvidenceDecision, snapshot: SpecificationSnapshot, details: tuple[str, ...]) -> EvidenceResult:
    # Non-goals never require positive proof; inspection limits are retained, not recast as prohibitions.
    status = EvidenceStatus.NOT_REQUIRED if decision.policy == EvidencePolicy.NON_GOAL else EvidenceStatus.UNSUPPORTED
    return EvidenceResult(status, decision.policy, snapshot.revision,
                          (EvidenceStatus.UNSUPPORTED.value,) + details)


def surface_result(decision: EvidenceDecision, snapshot: SpecificationSnapshot, trees: tuple[ast.Module, ...]) -> EvidenceResult:
    surface = inspect_surface(trees)
    matches = capability_matches(decision.subject, surface.names)
    if decision.policy == EvidencePolicy.NON_GOAL:
        requested = {name for subject in decision.required_subjects for name in capability_matches(subject, matches)}
        matches = tuple(name for name in matches if name not in requested)
        findings = () if decision.scope_permitted else tuple(f"unrequested_surface_detected:{name}" for name in matches)
        return EvidenceResult(EvidenceStatus.NOT_REQUIRED, decision.policy, snapshot.revision,
                              ("No positive acceptance proof required; capability was not explicitly prohibited.",), findings)
    if not known_capability(decision.subject):
        return unsupported(decision, snapshot, ("no declared API vocabulary for this prohibition",))
    if matches:
        return EvidenceResult(EvidenceStatus.FAIL, decision.policy, snapshot.revision,
                              tuple(f"forbidden_public_capability:{name}" for name in matches))
    if not surface.complete:
        return unsupported(decision, snapshot, ("public API may be dynamically extended",))
    return EvidenceResult(EvidenceStatus.PASS, decision.policy, snapshot.revision,
                          ("no matching capability in complete declared public API",))


def quality_result(decision: EvidenceDecision, snapshot: SpecificationSnapshot, trees: tuple[ast.Module, ...]) -> EvidenceResult:
    if decision.subject.strip().rstrip(".") not in {"coding-principles limits", "existing coding-principles limits", "coding principles"}:
        return unsupported(decision, snapshot, ("quality phrase has no configured deterministic gate",))
    from scripts.check_coding_principles import scan_class, scan_source_packing
    from pathlib import Path
    failures: list[str] = []
    for file, tree in zip((file for file in snapshot.files if production_python(file)), trees):
        scan_source_packing(Path(file.path), file.source, tree, failures)
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                scan_class(Path(file.path), node, failures)
    status = EvidenceStatus.FAIL if failures else EvidenceStatus.PASS
    return EvidenceResult(status, decision.policy, snapshot.revision, tuple(failures) or ("existing coding-principles static limits satisfied",))
