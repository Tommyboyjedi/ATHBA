"""Language-neutral draft ownership and selected-source projection."""
from hashlib import sha256
from pathlib import PurePosixPath

from core.development.specification_domain import SourceRequirementClause


def draft_artifact_path(scenario_id: str, canonical_path: str) -> str:
    name = PurePosixPath(canonical_path).name
    identity = sha256(scenario_id.encode("utf-8")).hexdigest()[:16]
    return f".athba/scenario-drafts/{identity}/{name}"


def selected_source_payload(clause: SourceRequirementClause) -> dict[str, object]:
    payload: dict[str, object] = {"ref": clause.ref, "text": clause.text,
                                  "kind": clause.kind, "obligation_type": clause.obligation_type}
    if clause.subject and clause.subject != clause.text:
        payload["source_excerpt"] = clause.subject
    return payload
