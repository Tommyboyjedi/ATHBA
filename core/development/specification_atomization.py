from __future__ import annotations

from core.development.mechanical_checklist_split import validate_mechanical_children

import json
import re

from core.development.checklist_split_progress import ChecklistSplitAncestry, rejected_split
from dataclasses import dataclass, field, replace
from typing import Sequence

from core.development.tdd_progression import SpecificationChecklist, SpecificationChecklistItem
from core.development.specification_domain import ChecklistAtomizationAttempt
from core.execution.reasoning_gateway import ReasoningGateway, ReasoningRequest


@dataclass(frozen=True)
class ChecklistAtomizationRequest:
    project_id: str
    requirement_text: str


MAX_ATOMIZER_SUBMISSIONS = 2
MAX_SPLIT_SUBMISSIONS = 2


class ChecklistAtomizationFailure(Exception):
    def __init__(self, attempts: tuple[ChecklistAtomizationAttempt, ...]):
        if len(attempts) != MAX_ATOMIZER_SUBMISSIONS:
            raise ValueError("atomization failure requires both bounded attempts")
        self.attempts = attempts
        super().__init__("specification checklist atomization failed after bounded schema repair")


@dataclass(frozen=True)
class ChecklistAtomizationResult:
    checklist: SpecificationChecklist
    attempts: tuple[ChecklistAtomizationAttempt, ...]


@dataclass(frozen=True)
class ChecklistSplitRequest:
    project_id: str
    requirement_text: str
    parent_ref: str
    parent_text: str
    parent_kind: str
    parent_modality: str
    parent_source_quote: str
    parent_subject: str
    individual_no_results: Sequence[dict[str, object]]
    final_revision: str
    ancestry: ChecklistSplitAncestry = field(default_factory=ChecklistSplitAncestry)


@dataclass(frozen=True)
class ChecklistSplitResponse:
    disposition: str
    rationale: str
    children: tuple[SpecificationChecklistItem, ...] = ()
    attempted_response: str = ""
    rejection_reason: str | None = None
    attempts: tuple[ChecklistAtomizationAttempt, ...] = ()

    def __post_init__(self) -> None:
        if self.disposition not in {"split", "unsplittable", "exhausted"}:
            raise ValueError("checklist split disposition must be split, unsplittable or exhausted")
        if not self.rationale.strip():
            raise ValueError("checklist split rationale is required")
        if self.disposition == "split" and len(self.children) < 2:
            raise ValueError("checklist split requires at least two children")
        if self.disposition != "split" and self.children:
            raise ValueError("unsplittable checklist split cannot contain children")


class SpecificationChecklistPlanner:
    """Create an independent specification checklist from one component requirement."""

    def __init__(self, gateway: ReasoningGateway):
        self.gateway = gateway

    async def create_checklist(self, request: ChecklistAtomizationRequest) -> SpecificationChecklist:
        return (await self.atomize(request)).checklist

    async def atomize(self, request: ChecklistAtomizationRequest) -> ChecklistAtomizationResult:
        result = await self.gateway.reason(_reasoning_request(request))
        try:
            checklist = _decode_checklist(request, result.text)
        except (ValueError, KeyError, TypeError) as error:
            initial_attempt = ChecklistAtomizationAttempt(result.text, str(error))
            repaired = await self.gateway.reason(_atomization_repair_request(request, result.text, str(error)))
            try:
                checklist = _decode_checklist(request, repaired.text)
            except (ValueError, KeyError, TypeError) as repair_error:
                raise ChecklistAtomizationFailure((
                    initial_attempt,
                    ChecklistAtomizationAttempt(repaired.text, str(repair_error)),
                )) from repair_error
            return ChecklistAtomizationResult(
                checklist,
                (initial_attempt, ChecklistAtomizationAttempt(repaired.text)),
            )
        return ChecklistAtomizationResult(checklist, (ChecklistAtomizationAttempt(result.text),))

    async def split_item(self, request: ChecklistSplitRequest) -> ChecklistSplitResponse:
        result = await self.gateway.reason(_split_reasoning_request(request))
        try:
            split = _decode_split(request, result.text)
        except (ValueError, KeyError, TypeError) as error:
            initial_attempt = ChecklistAtomizationAttempt(result.text, str(error))
            repaired = await self.gateway.reason(_split_repair_request(request, result.text, str(error)))
            try:
                split = _decode_split(request, repaired.text)
            except (ValueError, KeyError, TypeError) as repair_error:
                return ChecklistSplitResponse(
                    "exhausted",
                    f"checklist split validation failed after bounded schema repair: {repair_error}",
                    attempted_response=repaired.text,
                    rejection_reason="invalid_split_response_exhausted",
                    attempts=(
                        initial_attempt,
                        ChecklistAtomizationAttempt(repaired.text, str(repair_error)),
                    ),
                )
            return replace(
                split,
                attempts=(initial_attempt, ChecklistAtomizationAttempt(repaired.text)),
            )
        return replace(split, attempts=(ChecklistAtomizationAttempt(result.text),))


def _decode_split(request: ChecklistSplitRequest, response: str) -> ChecklistSplitResponse:
    payload = _json_object(response, label="checklist split")
    disposition, rationale = payload.get("disposition"), payload.get("rationale")
    if not isinstance(disposition, str) or not isinstance(rationale, str):
        raise ValueError("checklist split requires disposition and rationale")
    if disposition == "unsplittable":
        return ChecklistSplitResponse(disposition, rationale, attempted_response=response)
    raw_children = payload.get("children")
    if disposition != "split" or not isinstance(raw_children, list):
        raise ValueError("checklist split response is invalid")
    parent = SpecificationChecklistItem(request.parent_ref, request.parent_text,
        request.parent_kind, request.parent_modality, request.parent_source_quote, request.parent_subject)
    children = tuple(_validated_children(parent, request.requirement_text, raw_children))
    validate_mechanical_children(parent, children)
    reason = rejected_split(parent, children, request.ancestry)
    if reason is not None:
        raise ValueError(reason)
    return ChecklistSplitResponse("split", rationale, children, response)



def _reasoning_request(request: ChecklistAtomizationRequest) -> ReasoningRequest:
    return ReasoningRequest(
        purpose="athba_specification_checklist",
        prompt=_checklist_prompt(
            project_id=request.project_id,
            requirement_text=request.requirement_text,
        ),
        project_id=request.project_id,
        requires_large_context=False,
    )


def _atomization_repair_request(
    request: ChecklistAtomizationRequest,
    invalid_response: str,
    validation_error: str,
) -> ReasoningRequest:
    return ReasoningRequest(
        purpose="athba_specification_checklist_repair",
        prompt=json.dumps({
            "instruction": "Repair the invalid ATHBA Specification Deducer checklist for the Specification Gatekeeper. Return the complete corrected checklist as raw JSON only.",
            "project_id": request.project_id,
            "original_requirement": request.requirement_text,
            "invalid_checklist_draft": invalid_response,
            "validation_error": validation_error,
            "required_output_schema": _checklist_output_schema(),
            "rules": _atomization_rules(),
            "repair_rules": [
                "correct every contract violation visible in the complete invalid draft, not only the single validation error reported",
                "do not shorten a source_quote if doing so removes wording necessary to establish modality",
                "when repairing another field such as kind, retain already-valid provenance unless changing it is necessary to satisfy the contract",
            ],
            "output_rules": [
                "return raw JSON only",
                "do not wrap the JSON in Markdown",
                "do not use code fences",
                "do not add commentary before or after the JSON",
                "return the complete corrected checklist",
            ],
        }, indent=2, sort_keys=True),
        project_id=request.project_id,
        requires_large_context=False,
    )


def _checklist_prompt(*, project_id: str, requirement_text: str) -> str:
    return json.dumps(
        {
            "instruction": "Act as ATHBA's Specification Deducer for the Specification Gatekeeper. Return raw JSON only.",
            "project_id": project_id,
            "requirement_text": requirement_text,
            "output_rules": [
                "return raw JSON only",
                "do not wrap the JSON in Markdown",
                "do not use code fences",
                "do not add commentary before or after the JSON",
                "include exactly one top-level items array",
                "do not add extra fields outside the required schema",
            ],
            "required_output_schema": _checklist_output_schema(),
            "rules": _atomization_rules(),
        },
        indent=2,
        sort_keys=True,
    )


def _atomization_rules() -> list[str]:
    return [
        "one semantic obligation per item",
        "kind=validation without explicit source rejection uses obligation_type=precondition; with explicit rejection it uses error_behavior",
        "kind=invariant uses obligation_type=invariant; kind=behavior uses observable_behavior unless explicit source errors require error_behavior",
        "kind=constraint or kind=quality uses non_persistence_assurance for in-memory/no-persistence authority, naming for explicit lexical authority, and mechanical_assurance for other assurances",
        "positive persistence across storage/session boundaries is observable_behavior, never absence assurance",
        "validation without explicit rejection/error is a caller precondition; outside-domain behavior is unspecified",
        "do not invent runtime validation, exceptions or rejection from domain constraints",
        "read/nonmutation is an observable invariant proved by repeated public observations; do not require an internal-state proof",
        "every checklist item ref must be unique within the complete checklist",
        "modality is mandatory: required, forbidden, or non_goal; kind remains independent",
        "not required, optional, and out of scope mean modality=non_goal",
        "must not, do not implement, and must not exist mean modality=forbidden",
        "never convert non_goal into forbidden merely to satisfy kind validation",
        "non_goal must never be a kind",
        "text is the interpreted obligation and may use terminology different from the original source",
        "for modality=non_goal, source_quote must retain not required, optional, out of scope, or No ... are required wording",
        "for modality=forbidden, source_quote must retain must not, shall not, do not implement, forbidden, or prohibited wording",
        "source_quote must cite supporting words copied from one original source passage; full exact source excerpts remain the simplest option",
        "source_quote may omit intervening source words, with or without ... or …, but retained words must be complete tokens in source order within one passage",
        "source_quote need not be unique across checklist items",
        "multiple obligations may cite the same original passage when that passage supports each obligation",
        "subject must occur entirely within one actual retained contiguous source run, never across or inside omitted text",
        "retain verbatim source_quote and subject; never strengthen wording",
        "split enumerated capabilities and compound quality requirements into separate items",
        "preserve happy paths",
        "preserve failure cases",
        "preserve invariants",
        "preserve constraints",
        "preserve explicit quality and non-functional requirements where applicable",
        "do not invent unrelated requirements",
        "do not merge distinct behaviors simply because they appear in the same sentence",
        "kind must be one of behavior, validation, invariant, constraint, quality",
        "return specification facts only; do not select tests, reviews, mechanical checks, or any proof method",
        "do not include worker ids, model ids, GPU ids, endpoints, or ports",
    ]


def _checklist_output_schema() -> dict[str, object]:
    return {
        "items": [{
            "ref": "string",
            "text": "string",
            "kind": "behavior|validation|invariant|constraint|quality",
            "modality": "required|forbidden|non_goal",
            "source_quote": "supporting words copied from one original source passage; full excerpt or ordered complete tokens with optional .../… omissions",
            "subject": "source-backed capability or quality phrase contained in one retained source run",
            "obligation_type": "observable_behavior|precondition|error_behavior|invariant|mechanical_assurance|non_persistence_assurance|naming",
        }]
    }


def _decode_checklist(request: ChecklistAtomizationRequest, response: str) -> SpecificationChecklist:
    payload = _json_object(response, label="specification checklist")
    raw_items = payload.get("items")
    if not isinstance(raw_items, list):
        raise ValueError("specification checklist response must include an items list")
    return SpecificationChecklist(
        project_id=request.project_id,
        requirement_text=request.requirement_text,
        items=[item for item in _grounded_items(raw_items, request.requirement_text)],
    )


def _grounded_items(raw_items: list[object], source: str) -> list[SpecificationChecklistItem]:
    """Report every item error to the same bounded corrective submission."""
    items: list[SpecificationChecklistItem] = []
    errors: list[str] = []
    for index, raw in enumerate(raw_items):
        try:
            if not isinstance(raw, dict):
                raise ValueError("checklist item must be a JSON object")
            items.append(_grounded_item(raw, source))
        except (ValueError, KeyError, TypeError) as error:
            ref = raw.get("ref", index) if isinstance(raw, dict) else index
            errors.append(f"item {ref}: {error}")
    if errors:
        raise ValueError("checklist item validation errors:\n" + "\n".join(errors))
    return items


def _json_object(text: str, *, label: str) -> dict[str, object]:
    normalized = text.strip()
    fenced = re.fullmatch(
        r"```json[ \t]*\r?\n(?P<body>.*?)\r?\n```",
        normalized,
        flags=re.DOTALL | re.IGNORECASE,
    )
    if fenced is not None:
        normalized = fenced.group("body").strip()

    try:
        payload = json.loads(normalized)
    except json.JSONDecodeError as error:
        raise ValueError(f"{label} response was not valid JSON") from error
    if not isinstance(payload, dict):
        raise ValueError(f"{label} response must be a JSON object")
    return payload


def _grounded_item(payload: dict[str, object], source: str) -> SpecificationChecklistItem:
    for name in ("modality", "source_quote", "subject"):
        if not isinstance(payload.get(name), str) or not str(payload[name]).strip():
            raise ValueError(f"specification checklist requires explicit {name}")
    try:
        item = SpecificationChecklistItem.from_dict(payload)
    except ValueError as error:
        ref = str(payload.get("ref", "<unknown>"))
        field = "modality" if "modality" in str(error) or "non-goal" in str(error) else "item"
        raise ValueError(f"{error}: item {ref} field {field}") from error
    item.source_context(source)
    return item



def _validated_children(parent: SpecificationChecklistItem, source: str, raw_children: list[object]) -> list[SpecificationChecklistItem]:
    if len(raw_children) < 2:
        raise ValueError("checklist split requires at least two children")
    children: list[SpecificationChecklistItem] = []
    for index, raw in enumerate(raw_children, 1):
        if not isinstance(raw, dict):
            raise ValueError("checklist split children must be objects")
        payload = dict(raw)
        payload["ref"] = f"{parent.ref}-S{index:03d}"
        child = _grounded_item(payload, source)
        children.append(child)
    return children


def _split_reasoning_request(request: ChecklistSplitRequest) -> ReasoningRequest:
    return ReasoningRequest(
        purpose="athba_specification_checklist_split",
        project_id=request.project_id,
        requires_large_context=False,
        prompt=json.dumps({
            "instruction": "Act as ATHBA's independent Specification Deducer for the Specification Gatekeeper. Return raw JSON only.",
            "original_requirement": request.requirement_text,
            "parent": {"ref": request.parent_ref, "text": request.parent_text, "kind": request.parent_kind,
                       "modality": request.parent_modality, "source_quote": request.parent_source_quote,
                       "subject": request.parent_subject},
            "individual_test_no_results": list(request.individual_no_results),
            "final_trusted_revision": request.final_revision,
            "question": "Split this unresolved checklist item into two or more smaller independent specification obligations that together preserve the parent.",
            "required_output": _split_output_schema(),
            "rules": _split_rules(),
            "output_rules": [
                "return raw JSON only",
                "do not wrap the JSON in Markdown",
                "do not use code fences",
                "do not add commentary before or after the JSON",
            ],
        }, sort_keys=True),
    )


def _split_repair_request(
    request: ChecklistSplitRequest,
    invalid_response: str,
    validation_error: str,
) -> ReasoningRequest:
    return ReasoningRequest(
        purpose="athba_specification_checklist_split_repair",
        project_id=request.project_id,
        requires_large_context=False,
        prompt=json.dumps({
            "instruction": "Repair the invalid ATHBA Specification Deducer split response for the Specification Gatekeeper. Return the complete corrected split response as raw JSON only.",
            "original_requirement": request.requirement_text,
            "parent": {"ref": request.parent_ref, "text": request.parent_text, "kind": request.parent_kind,
                       "modality": request.parent_modality, "source_quote": request.parent_source_quote,
                       "subject": request.parent_subject},
            "individual_test_no_results": list(request.individual_no_results),
            "final_trusted_revision": request.final_revision,
            "invalid_split_draft": invalid_response,
            "validation_error": validation_error,
            "required_output": _split_output_schema(),
            "rules": _split_rules(),
            "repair_rules": [
                "correct every contract violation visible in the invalid draft, not only the single validation error reported",
                "if no valid grounded split is possible, return disposition=unsplittable with a precise rationale",
                "do not weaken provenance, ordered-source citation, kind, or modality rules to make a split pass",
            ],
            "output_rules": [
                "return raw JSON only",
                "do not wrap the JSON in Markdown",
                "do not use code fences",
                "do not add commentary before or after the JSON",
                "return the complete corrected split response",
            ],
        }, indent=2, sort_keys=True),
    )


def _split_output_schema() -> dict[str, object]:
    return {
        "disposition": "split|unsplittable",
        "rationale": "string",
        "children": [{
            "text": "string",
            "kind": "behavior|validation|invariant|constraint|quality",
            "modality": "required|forbidden|non_goal",
            "source_quote": "supporting words copied from one original source passage; full excerpt or ordered complete tokens with optional .../… omissions",
            "subject": "source-backed capability or quality phrase contained in one retained source run",
        }],
    }


def _split_rules() -> list[str]:
    return [
        "do not select tests",
        "do not inspect Behavior Planner output",
        "do not inspect production code",
        "do not add obligations",
        "preserve modality unless the parent was itself invalid",
        "return unsplittable if no grounded progress is possible",
        "each split child must be one semantic obligation from the parent item",
        "split children together must preserve the parent item without adding new requirements",
        "for a compound mechanical constraint, partition every conjunct exactly once; keep kind, modality, and the same complete parent source_quote; each child needs an independent bounded policy",
        "text is the interpreted obligation and may use terminology different from the original source",
        "for modality=non_goal, source_quote must retain not required, optional, out of scope, or No ... are required wording",
        "for modality=forbidden, source_quote must retain must not, shall not, do not implement, forbidden, or prohibited wording",
        "source_quote must cite supporting words copied from one original source passage; full exact source excerpts remain the simplest option",
        "source_quote may omit intervening source words, with or without ... or …, but retained words must be complete tokens in source order within one passage",
        "source_quote need not be unique across checklist items",
        "multiple obligations may cite the same original passage when that passage supports each obligation",
        "subject must occur entirely within one actual retained contiguous source run, never across or inside omitted text",
        "retain verbatim source_quote and subject; never strengthen wording",
        "kind must be one of behavior, validation, invariant, constraint, quality",
        "modality must be one of required, forbidden, non_goal",
    ]
