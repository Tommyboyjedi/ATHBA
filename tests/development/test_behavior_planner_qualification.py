import hashlib
import inspect
import json
import re

from core.development import behavior_planner_qualification
from core.development.behavior_planner_qualification import (
    behavior_planner_qualification_fixture_path,
    load_behavior_planner_qualification_v1,
)


EXPECTED_CASE_HASHES = {
    "BPQ-V1-A": "6a88d231bc489d24507b0b9a7abbc61bd6e13e418a0d65567490da25c72eea36",
    "BPQ-V1-B": "c46ce04d165b64d2459fdd821475289925496dc7541584230d60f4858ec9aa88",
    "BPQ-V1-C": "65fe74ab5a04edd6b3e1cecd6a93da5b2b05ad45d973b131f712c8a4678d78bd",
}
EXPECTED_CORPUS_SHA256 = "523dc088007cdcd10484daa7cb272fdbdab4a37a306a5369bbeac1ff676d85cb"


def test_bpq_v1_has_the_exact_frozen_case_identity_and_text_hashes():
    corpus = load_behavior_planner_qualification_v1()

    assert corpus.version == "BPQ-V1"
    assert [case.fixture_id for case in corpus.cases] == [
        "BPQ-V1-A",
        "BPQ-V1-B",
        "BPQ-V1-C",
    ]
    assert [case.component_name for case in corpus.cases] == [
        "ReservationBook",
        "SignalBoard",
        "ParcelLocker",
    ]
    assert len(corpus.cases) == 3
    assert sorted(
        path.name
        for path in behavior_planner_qualification_fixture_path().parent.glob("*.json")
    ) == ["behavior_planner_qualification_v1.json"]
    assert {
        case.fixture_id: case.requirement_text_sha256 for case in corpus.cases
    } == EXPECTED_CASE_HASHES
    assert corpus.corpus_sha256 == EXPECTED_CORPUS_SHA256


def test_bpq_v1_loader_reads_the_canonical_fixture_without_inline_requirements():
    fixture_payload = json.loads(
        behavior_planner_qualification_fixture_path().read_text(encoding="utf-8")
    )
    corpus = load_behavior_planner_qualification_v1()

    assert fixture_payload["corpus_version"] == corpus.version
    assert [
        (item["id"], item["component_name"], item["requirement_text"])
        for item in fixture_payload["cases"]
    ] == [
        (case.fixture_id, case.component_name, case.requirement_text)
        for case in corpus.cases
    ]

    loader_source = inspect.getsource(behavior_planner_qualification)
    for case in corpus.cases:
        assert case.requirement_text not in loader_source


def test_bpq_v1_requirements_are_prose_not_pre_authored_test_instructions():
    corpus = load_behavior_planner_qualification_v1()

    for case in corpus.cases:
        assert chr(96) * 3 not in case.requirement_text

    for fixture_id in ("BPQ-V1-B", "BPQ-V1-C"):
        requirement_text = next(
            case.requirement_text
            for case in corpus.cases
            if case.fixture_id == fixture_id
        )
        assert re.search(r"(?m)^\s*(?:\d+[.)]|[-*])\s+", requirement_text) is None
        assert "assert " not in requirement_text.lower()
        assert "pytest" not in requirement_text.lower()


def test_bpq_v1_requirement_hashes_are_utf8_hashes():
    corpus = load_behavior_planner_qualification_v1()

    assert {
        case.fixture_id: hashlib.sha256(
            case.requirement_text.encode("utf-8")
        ).hexdigest()
        for case in corpus.cases
    } == EXPECTED_CASE_HASHES
