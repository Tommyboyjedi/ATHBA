from __future__ import annotations

import json
import re

from core.development.checklist_split_progress import ChecklistSplitAncestry, rejected_split
from dataclasses import dataclass, field
from typing import Sequence

from core.development.tdd_progression import SpecificationChecklist, SpecificationChecklistItem
from core.development.specification_domain import ChecklistAtomizationAttempt
from core.execution.reasoning_gateway import ReasoningGateway, ReasoningRequest


@dataclass(frozen=True)
class ChecklistAtomizationRequest:
    project_id: str
    requirement_text: str


MAX_ATOMIZER_SUBMISSIONS = 2


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

    def __post_init__(self) -> None:
        if self.disposition not in {"split", "unsplittable"}:
            raise ValueError("checklist split disposition must be split or unsplittable")
        if not self.rationale.strip():
            raise ValueError("checklist split rationale is required")
        if self.disposition == "split" and len(self.children) < 2:
            raise ValueError("checklist split requires at least two children")
        if self.disposition == "unsplittable" and self.children:
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
            return ChecklistSplitResponse("unsplittable", str(error), attempted_response=result.text,
                                          rejection_reason="invalid_split_response")
        return split


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
    reason = rejected_split(parent, children, request.ancestry)
    if reason is not None:
        return ChecklistSplitResponse("unsplittable", rationale, attempted_response=response,
                                      rejection_reason=reason)
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
            "instruction": "Repair the invalid ATHBA Specification Gatekeeper checklist. Return the complete corrected checklist as raw JSON only.",
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
            "instruction": "Act as ATHBA's Specification Gatekeeper atomizer. Return raw JSON only.",
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
        "every checklist item ref must be unique within the complete checklist",
        "modality is mandatory: required, forbidden, or non_goal; kind remains independent",
        "not required, optional, and out of scope mean modality=non_goal",
        "must not, do not implement, and must not exist mean modality=forbidden",
        "never convert non_goal into forbidden merely to satisfy kind validation",
        "non_goal must never be a kind",
        "source_quote must contain enough contiguous original wording to establish the declared modality",
        "for modality=non_goal, source_quote must retain not required, optional, out of scope, or No ... are required wording",
        "for modality=forbidden, source_quote must retain must not, shall not, do not implement, forbidden, or prohibited wording",
        "when one compound source sentence establishes modality for several atomic items, those items may reuse the same full source_quote while subject narrows each obligation",
        "source_quote need not be unique across checklist items",
        "source_quote may use ... between non-empty verbatim segments in source order within one sentence/clause; never cross sentence or clause boundaries or splice words",
        "an omission subject must occur entirely within one retained verbatim segment, never across or inside omitted text",
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
            "source_quote": "verbatim contiguous excerpt from requirement_text, or ordered verbatim segments separated by ... within one source clause",
            "subject": "verbatim capability or quality phrase within source_quote",
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
        items=[_grounded_item(dict(item), request.requirement_text) for item in raw_items],
    )


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
    item = SpecificationChecklistItem.from_dict(payload)
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
            "instruction": "Act as ATHBA's independent Specification Gatekeeper atomizer. Return raw JSON only.",
            "original_requirement": request.requirement_text,
            "parent": {"ref": request.parent_ref, "text": request.parent_text, "kind": request.parent_kind,
                       "modality": request.parent_modality, "source_quote": request.parent_source_quote,
                       "subject": request.parent_subject},
            "individual_test_no_results": list(request.individual_no_results),
            "final_trusted_revision": request.final_revision,
            "question": "Split this unresolved checklist item into two or more smaller independent specification obligations that together preserve the parent.",
            "required_output": {"disposition": "split|unsplittable", "rationale": "string",
                "children": [{"text": "string", "kind": "behavior|validation|invariant|constraint|quality",
                "modality": "required|forbidden|non_goal", "source_quote": "verbatim source excerpt", "subject": "source phrase"}]},
            "rules": ["do not select tests", "do not inspect Behavior Planner output", "do not inspect production code",
                      "do not add obligations", "preserve modality", "return unsplittable if no grounded progress is possible"],
        }, sort_keys=True),
    )
