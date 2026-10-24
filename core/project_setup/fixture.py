"""Explicit test-only architectural handoff; never a production approval issuer."""
from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path

from core.filesystem_policy import resolve_relative_path
from core.project_setup.architecture import (
    ApprovedArchitecture, ArchitectureApproval, ArchitectureDecision, ApprovalKind,
    ApprovalStatus, FullBehavior, content_hash,
)
from core.project_setup.profile_domain import ProfileKind, ProfileSelection, ToolKind, ToolSelection


@dataclass(frozen=True)
class FixtureBinding:
    directory: Path
    project_id: str


def fixture_specification(directory: Path) -> dict:
    fixture = json.loads((directory / "approved_architecture.json").read_text())
    return {"sections": [{"name": item["id"], "body": resolve_relative_path(
                directory, item["source_file"], "fixture source").read_bytes().decode()}
             for item in fixture["behaviors"]],
            "meta": {"fixture_id": fixture["fixture_id"], "test_fixture_only": True}}


def load_test_architecture(request: FixtureBinding) -> ApprovedArchitecture:
    fixture = json.loads((request.directory / "approved_architecture.json").read_text())
    approval = fixture["approval"]
    if not fixture.get("fixture_only") or approval.get("label") != "TEST_FIXTURE":
        raise ValueError("not an explicitly labelled architecture test fixture")
    data = fixture["profile_selection"]
    profile = ProfileSelection(
        ProfileKind(data["name"]), tuple(data["technologies"]),
        tuple(ToolSelection(ToolKind(item["kind"]), item["executable"], item["version"])
              for item in data["tools"]),
        data["execution_context"], data["dependency_policy"],
        data.get("framework"), data.get("project_language"), data.get("template"),
    )
    behaviors = tuple(FullBehavior(
        item["id"], resolve_relative_path(request.directory, item["source_file"], "fixture source").read_bytes().decode(),
        item["source_sha256"], tuple(item["production_paths"]), tuple(item["test_paths"]),
        tuple(item.get("depends_on", ()))) for item in fixture["behaviors"])
    if tuple(fixture["delivery_order"]) != tuple(item.id for item in behaviors):
        raise ValueError("fixture delivery order differs from approved source identities")
    decision = ArchitectureDecision(
        request.project_id, fixture["specification_version"], content_hash(fixture_specification(request.directory)),
        1, fixture["application_kind"], profile, behaviors,
    )
    receipt = ArchitectureApproval(
        approval["identity"], request.project_id, decision.digest, ApprovalKind.TEST_FIXTURE,
        ApprovalStatus(approval["state"]), bool(approval["binding_conflicts_resolved"]),
    )
    return ApprovedArchitecture(decision, receipt)
