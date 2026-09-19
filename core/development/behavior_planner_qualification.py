"""Canonical, versioned Behavior Planner qualification corpus loading."""

from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path


_FIXTURE_PATH = (
    Path(__file__).resolve().parents[2]
    / "qualification_fixtures"
    / "behavior_planner_qualification_v1.json"
)


@dataclass(frozen=True)
class BehaviorPlannerQualificationCase:
    fixture_id: str
    component_name: str
    requirement_text: str

    @property
    def requirement_text_sha256(self) -> str:
        return sha256(self.requirement_text.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class BehaviorPlannerQualificationCorpus:
    version: str
    cases: tuple[BehaviorPlannerQualificationCase, ...]

    @property
    def corpus_sha256(self) -> str:
        return sha256(
            json.dumps(
                {
                    "corpus_version": self.version,
                    "cases": [
                        {
                            "id": case.fixture_id,
                            "component_name": case.component_name,
                            "requirement_text": case.requirement_text,
                        }
                        for case in self.cases
                    ],
                },
                ensure_ascii=False,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()


def behavior_planner_qualification_fixture_path() -> Path:
    return _FIXTURE_PATH


def load_behavior_planner_qualification_v1() -> BehaviorPlannerQualificationCorpus:
    payload = json.loads(_FIXTURE_PATH.read_text(encoding="utf-8"))
    return BehaviorPlannerQualificationCorpus(
        version=str(payload["corpus_version"]),
        cases=tuple(
            BehaviorPlannerQualificationCase(
                fixture_id=str(item["id"]),
                component_name=str(item["component_name"]),
                requirement_text=str(item["requirement_text"]),
            )
            for item in payload["cases"]
        ),
    )
