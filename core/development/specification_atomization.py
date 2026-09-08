from __future__ import annotations

import json
import re

from core.development.specification_obligations import grounded_modality
from core.development.checklist_split_progress import ChecklistSplitAncestry, rejected_split
from dataclasses import dataclass, field
from typing import Sequence

from core.development.tdd_progression import SpecificationChecklist, SpecificationChecklistItem
from core.execution.reasoning_gateway import ReasoningGateway, ReasoningRequest


@dataclass(frozen=True)
class ChecklistAtomizationRequest:
    project_id: str
    requirement_text: str


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
        result = await self.gateway.reason(_reasoning_request(request))
        payload = _json_object(result.text, label="specification checklist")
        raw_items = payload.get("items")
        if not isinstance(raw_items, list):
            raise ValueError("specification checklist response must include an items list")
        return SpecificationChecklist(
            project_id=request.project_id,
            requirement_text=request.requirement_text,
            items=[_grounded_item(dict(item), request.requirement_text) for item in raw_items],
        )

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
            "required_output_schema": {
                "items": [
                    {
                        "ref": "string",
                        "text": "string",
                        "kind": "behavior|validation|invariant|constraint|quality",
                        "modality": "required|forbidden|non_goal",
                        "source_quote": "verbatim contiguous excerpt from requirement_text",
                        "subject": "verbatim capability or quality phrase within source_quote",
                    }
                ]
            },
            "rules": [
                "one semantic obligation per item",
                "modality is mandatory: required, forbidden, or non_goal; kind remains independent",
                "not required, optional, and out of scope mean non_goal, not forbidden",
                "do not implement and must not exist mean forbidden",
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
            ],
        },
        indent=2,
        sort_keys=True,
    )


def _json_object(text: str, *, label: str) -> dict[str, object]:
    try:
        payload = json.loads(text)
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
    if item.source_quote not in source or item.subject.lower() not in item.source_quote.lower():
        raise ValueError("specification checklist provenance is not grounded in original source")
    start = source.index(item.source_quote)
    left = max(source.rfind(mark, 0, start) for mark in (".", "!", "?", "\n")) + 1
    end = start + len(item.source_quote)
    boundaries = [position for mark in (".", "!", "?", "\n") if (position := source.find(mark, end)) >= 0]
    right = min(boundaries) if boundaries else len(source)
    context = source[left:right] if not re.search(r"[.!?]$", item.source_quote) else source[left:end]
    grounded_modality(item.modality, context)
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
