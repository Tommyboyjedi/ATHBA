"""Accepted-test supersession preserves immutable origin authority."""
from dataclasses import dataclass, replace
from pathlib import Path
import subprocess

import pytest

from core.development.consolidation_evidence import (
    ActiveAcceptedEvidenceResolver, ActiveEvidenceRequest, CaseSnapshot, CoverageLink, SupersessionRecord,
)
from core.development.python_test_material import PythonTestMaterial
from core.development.specification_reconciliation import AcceptedTestEvidence, GitAcceptedTestCatalog, TestCatalogRevision
from core.development.strict_tdd_feature_domain import StrictTddFeatureState
from core.development.test_material import TestModuleReplacementRequest, TestSourceRequest


def _git(root: Path, arguments: tuple[str, ...]) -> str:
    return subprocess.run(("git", *arguments), cwd=root, check=True, text=True, capture_output=True).stdout.strip()


def _commit(root: Path, message: str) -> str:
    _git(root, ("add", "."))
    _git(root, ("commit", "-qm", message))
    return _git(root, ("rev-parse", "HEAD"))


@dataclass(frozen=True)
class _EvidenceCase:
    root: Path
    base: str
    final: str
    original: tuple[AcceptedTestEvidence, ...]
    record: SupersessionRecord
    trusted_source: str
    replacement_source: str


@pytest.fixture
def evidence_case(tmp_path: Path) -> _EvidenceCase:
    _git(tmp_path, ("init", "-q"))
    _git(tmp_path, ("config", "user.name", "Test"))
    _git(tmp_path, ("config", "user.email", "test@example.invalid"))
    (tmp_path / "tests").mkdir()
    (tmp_path / "arithmetic.py").write_text("def measure(value):\n    return value * 2\n")
    trusted = ("from arithmetic import measure\n\n"
               "def test_A():\n    assert measure(2) == 4\n\n"
               "def test_B():\n    assert measure(3) == 6\n\n"
               "def test_unrelated():\n    assert measure(4) == 8\n")
    path = "tests/test_arithmetic.py"
    (tmp_path / path).write_text(trusted)
    base = _commit(tmp_path, "accepted original tests")
    material = PythonTestMaterial()
    names = tuple(f"{path}::test_{name}" for name in ("A", "B", "unrelated"))
    original = tuple(AcceptedTestEvidence(name, path, f"REQ-{ref}", [f"source-{ref}"], base, base)
                     for name, ref in zip(names, ("A", "B", "other")))
    previous = tuple(CaseSnapshot(item.test_name, path,
        material.extract(TestSourceRequest(trusted, item.test_name)) or "", base,
        (item.step_id,), tuple(item.requirement_refs)) for item in original[:2])
    replacement_name = f"{path}::test_combined"
    submitted = ("from arithmetic import measure\n\n"
                 "def test_combined():\n    assert measure(2) == 4\n    assert measure(3) == 6\n")
    merged = material.replace(TestModuleReplacementRequest(trusted, submitted, replacement_name, names[:2]))
    (tmp_path / path).write_text(merged)
    final = _commit(tmp_path, "replace selected tests without production changes")
    current = CaseSnapshot(replacement_name, path,
        material.extract(TestSourceRequest(submitted, replacement_name)) or "", final,
        ("REQ-A", "REQ-B"), ("source-A", "source-B"))
    refs = ("REQ-A", "REQ-B", *(item.observation_ref for item in previous), "fragment:opaque:assertion")
    coverage = tuple(CoverageLink(ref, replacement_name, "retains exact selected observations") for ref in refs)
    record = SupersessionRecord("checkpoint-1", ("REQ-A", "REQ-B"), previous, (current,),
        "Both independent examples share one source-grounded test", coverage, base, final, final, ("semantic:approved", "execution:green"))
    return _EvidenceCase(tmp_path, base, final, original, record, trusted, submitted)


def test_active_supersession_preserves_originals_and_has_no_fabricated_red(evidence_case: _EvidenceCase) -> None:
    case = evidence_case
    resolver = ActiveAcceptedEvidenceResolver(case.root, PythonTestMaterial())
    active = resolver.resolve(ActiveEvidenceRequest(case.original, (case.record,), case.final))
    assert {item.test_name for item in active} == {"tests/test_arithmetic.py::test_unrelated", "tests/test_arithmetic.py::test_combined"}
    consolidated = next(item for item in active if item.supersession_id)
    assert consolidated.red_revision is None
    assert consolidated.evidence_kind == "consolidated_green"
    assert consolidated.covered_requirement_refs == ("REQ-A", "REQ-B")
    assert all(item.red_revision == case.base for item in case.original)
    assert _git(case.root, ("show", f"{case.base}:tests/test_arithmetic.py")) == case.trusted_source.strip()
    catalog = GitAcceptedTestCatalog(case.root, TestCatalogRevision(case.final, PythonTestMaterial()))
    assert catalog.verified_source(consolidated) == case.record.replacement_tests[0].source
    assert catalog.verified_source(case.original[0]) is None
    state = StrictTddFeatureState("project", "source", "running",
        evidence_consolidations=(case.record,), consolidation_checks=("checkpoint-1",))
    assert StrictTddFeatureState.from_dict(state.to_dict()) == state
    assert StrictTddFeatureState.from_dict({"project_id": "old", "source_requirement_hash": "source", "status": "running"}).evidence_consolidations == ()


def test_supersession_rejects_missing_coverage_and_changed_unselected_source(evidence_case: _EvidenceCase) -> None:
    case = evidence_case
    with pytest.raises(ValueError, match="omits prior observation"):
        replace(case.record, coverage=case.record.coverage[:1])
    material = PythonTestMaterial()
    with pytest.raises(ValueError, match="overwrite an unselected"):
        material.replace(TestModuleReplacementRequest(case.trusted_source,
            "def test_unrelated():\n    assert True\n", "tests/test_arithmetic.py::test_unrelated",
            ("tests/test_arithmetic.py::test_A", "tests/test_arithmetic.py::test_B")))
    wrong = replace(case.record.previous_tests[0], source="def test_A():\n    assert True")
    forged = replace(case.record, previous_tests=(wrong, case.record.previous_tests[1]),
        coverage=(*case.record.coverage, CoverageLink(wrong.observation_ref,
            case.record.replacement_tests[0].name, "changed historical source")))
    resolver = ActiveAcceptedEvidenceResolver(case.root, material)
    with pytest.raises(ValueError, match="historical accepted source"):
        resolver.resolve(ActiveEvidenceRequest(case.original, (forged,), case.final))
    test_path = case.root / "tests/test_arithmetic.py"
    test_path.write_text(test_path.read_text().replace("measure(4) == 8", "measure(4) == 7"))
    changed = _commit(case.root, "tamper with unselected accepted evidence")
    with pytest.raises(ValueError, match="without supersession authority"):
        resolver.resolve(ActiveEvidenceRequest(case.original, (case.record,), changed))
