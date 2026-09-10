"""Decorator opacity is a visible assurance limit, never a blanket unknown bypass."""
from dataclasses import replace
import json
from pathlib import Path

import pytest

from core.development.python_specification_evidence import PythonSpecificationEvidenceAdapter
from core.development.specification_domain import SpecificationChecklistItem
from core.development.specification_evidence_policy import (
    EvidenceDecision, EvidenceStatus, RevisionFile, SpecificationSnapshot, reconciliation_satisfied,
)
from core.development.specification_evidence_routing import RoutedChecklistReconciler, RoutedChecklistRequest
from core.development.specification_obligations import EvidencePolicy, ObligationModality
from core.development.specification_reconciliation import ChecklistItemReconciler, GitAcceptedTestCatalog
from core.development.strict_tdd_feature_domain import StrictTddFeatureState
from core.development.strict_tdd_feature_store import StrictTddFeatureRepository
from core.development.strict_tdd_lifecycle_evidence import (
    StrictTddLifecycleRunContext, StrictTddProofReportBuilder, StrictTddProofReportInput,
)
from tests.development.test_test_evidence_reconciliation import FakeReasoningGateway, _repository, _commit_all

FIXTURE = Path(__file__).parent / "fixtures/pr30_decorated_accessor.json"
ASSURANCE = "Storage requirement passed by bounded static inspection; decorator effects were not statically verified."


def verify(source, metadata=()):
    snapshot = SpecificationSnapshot("a" * 40, (RevisionFile("component.py", source), *metadata))
    decision = EvidenceDecision(EvidencePolicy.STORAGE, "in memory", ObligationModality.REQUIRED)
    return PythonSpecificationEvidenceAdapter().verify(decision, snapshot)


def test_ordinary_storage_free_code_remains_pass_without_warning():
    result = verify("class Component:\n    def __init__(self):\n        self.value = 0\n")
    assert result.status == EvidenceStatus.PASS
    assert result.findings == ()
    assert result.details == ("canonical source and declarations satisfy the bounded static policy",)


@pytest.mark.parametrize("source,identity,line", [
    ("@opaque\ndef value():\n    return 0\n", "opaque", 1),
    ("@opaque\nasync def value():\n    return 0\n", "opaque", 1),
    ("class Component:\n    @property\n    def value(self):\n        return self._value\n", "property", 2),
    ("class Component:\n    @classmethod\n    def value(cls):\n        return 0\n", "classmethod", 2),
])
def test_function_decorator_opacity_passes_with_explicit_location_warning(source, identity, line):
    result = verify(source)
    assert result.status == EvidenceStatus.PASS
    assert result.details == (ASSURANCE,)
    assert result.findings == (
        f"assurance_warning: component.py:{line}: @{identity} on value; decorator effects were not statically verified",)


def test_exact_recorded_live_property_case_passes_with_retained_warning():
    fixture = json.loads(FIXTURE.read_text())
    result = verify(fixture["source"])
    assert result.status == EvidenceStatus.PASS
    assert result.details == (ASSURANCE,)
    assert result.findings == (
        "assurance_warning: component.py:14: @property on total; decorator effects were not statically verified",)


@pytest.mark.parametrize("source", [
    '@opaque\ndef store():\n    open("data", "w")\n',
    '@open("data", "w")\ndef store():\n    pass\n',
    *[f"import {module}\n@opaque\ndef store():\n    pass\n"
      for module in ("sqlite3", "dbm", "shelve", "pickle", "pathlib", "tempfile", "io", "os", "shutil")],
])
def test_decorator_warning_never_suppresses_positive_storage_detection(source):
    result = verify(source)
    assert result.status == EvidenceStatus.FAIL
    assert any("storage" in detail for detail in result.details)
    assert len(result.findings) == 1
    assert result.findings[0].startswith("assurance_warning:")
    assert ASSURANCE not in result.details


@pytest.mark.parametrize("source,reason", [
    ("@opaque\ndef work(callback):\n    callback()\n", "opaque call effects"),
    ("@opaque\ndef work(values):\n    return values[0]\n", "opaque protocol"),
    ("@opaque\ndef work(target):\n    return target.value\n", "opaque attribute"),
    ("import collections\n@opaque\ndef work():\n    pass\n", "imported runtime effects"),
    ("@opaque\ndef work():\n    __import__('custom')\n", "dynamic runtime"),
    ("@factory()\ndef work():\n    pass\n", "opaque call effects"),
    ("@registry.decorator\ndef work():\n    pass\n", "opaque attribute"),
    ("@opaque\nclass Component:\n    @opaque\n    def work(self):\n        pass\n", "opaque class"),
])
def test_other_unknowns_including_decorator_expressions_remain_blocking(source, reason):
    result = verify(source)
    assert result.status == EvidenceStatus.UNSUPPORTED
    assert any(reason in detail for detail in result.details)
    assert len(result.findings) == 1
    assert ASSURANCE not in result.details


def test_persistence_configuration_remains_blocking_and_keeps_warning():
    result = verify("@opaque\ndef work():\n    pass\n", (RevisionFile("storage.json", '{"backend":"unknown"}'),))
    assert result.status == EvidenceStatus.UNSUPPORTED
    assert any("unsupported persistence configuration" in detail for detail in result.details)
    assert len(result.findings) == 1


def test_multiple_warnings_have_deterministic_path_and_source_order():
    files = (
        RevisionFile("z.py", "@second\n@first\ndef outer():\n    @nested\n    def inner():\n        pass\n"),
        RevisionFile("a.py", "@last\ndef other():\n    pass\n"),
    )
    decision = EvidenceDecision(EvidencePolicy.STORAGE, "in memory", ObligationModality.REQUIRED)
    snapshot = SpecificationSnapshot("a" * 40, files)
    result = PythonSpecificationEvidenceAdapter().verify(decision, snapshot)
    reversed_result = PythonSpecificationEvidenceAdapter().verify(decision, replace(snapshot, files=tuple(reversed(files))))
    assert result.status == EvidenceStatus.PASS
    assert result.findings == reversed_result.findings == (
        "assurance_warning: a.py:1: @last on other; decorator effects were not statically verified",
        "assurance_warning: z.py:1: @second on outer; decorator effects were not statically verified",
        "assurance_warning: z.py:2: @first on outer; decorator effects were not statically verified",
        "assurance_warning: z.py:4: @nested on inner; decorator effects were not statically verified",
    )


@pytest.mark.asyncio
async def test_final_gatekeeper_warning_survives_disk_reload_and_final_report_packet(tmp_path):
    repo = tmp_path / "repository"
    repo.mkdir()
    _repository(repo)
    source = json.loads(FIXTURE.read_text())["source"]
    (repo / "reservation_book.py").write_text(source)
    revision = _commit_all(repo, "recorded decorated accessor")
    catalog = GitAcceptedTestCatalog(repo, revision)
    gateway = FakeReasoningGateway([])
    reconciler = RoutedChecklistReconciler(ChecklistItemReconciler(gateway, catalog), catalog)
    original = "Keep the implementation dependency-free and in memory."
    item = SpecificationChecklistItem("memory", "Keep the implementation in memory.",
        "constraint", "required", "Keep the implementation ... in memory", "in memory")
    record = await reconciler.reconcile(RoutedChecklistRequest("project-one", item, original, []))
    assert record["answer"] == "YES"
    assert record["evidence_policy"] == "no_storage"
    assert record["rationale"] == ASSURANCE
    warning = "assurance_warning: reservation_book.py:14: @property on total; decorator effects were not statically verified"
    assert record["findings"] == [warning]
    assert reconciliation_satisfied((record,))
    assert not gateway.requests
    state = StrictTddFeatureState("project-one", "requirement-hash", "completed", final_reconciliation=(record,))
    store = StrictTddFeatureRepository(tmp_path / "features")
    store.save(state)
    restored = StrictTddFeatureRepository(tmp_path / "features").load("project-one")
    assert restored.final_reconciliation == state.final_reconciliation
    context = StrictTddLifecycleRunContext("run-one", "project-one", original, "athba-test", "rack-test")
    report = StrictTddProofReportBuilder().build(StrictTddProofReportInput(context, restored, (), (), ()))
    packet = report.structured["sections"]["final_reconciliation"]["value"][0]
    assert packet["answer"] == "YES" and packet["findings"] == [warning]
    assert packet["rationale"] == ASSURANCE
    assert warning in report.markdown and ASSURANCE in report.markdown
    from core.development.post_behavior_evidence import PostBehaviorEvidenceStore
    evidence = PostBehaviorEvidenceStore(tmp_path / "post-behavior")
    reference = evidence.record("specification_reconciliation", {"results": [packet]})
    assert json.loads(Path(reference).read_text())["payload"]["results"][0]["findings"] == [warning]


def test_decorators_do_not_change_dependency_policy_evidence():
    decision = EvidenceDecision(EvidencePolicy.DEPENDENCY, "dependency-free", ObligationModality.REQUIRED)
    snapshot = SpecificationSnapshot("a" * 40, (RevisionFile("component.py", "@opaque\ndef work():\n    pass\n"),))
    result = PythonSpecificationEvidenceAdapter().verify(decision, snapshot)
    assert result.status == EvidenceStatus.PASS
    assert result.findings == ()
