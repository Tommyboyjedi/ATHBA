from __future__ import annotations

import json
import re

from core.development.specification_obligations import grounded_modality
from dataclasses import dataclass

from core.development.tdd_progression import SpecificationChecklist, SpecificationChecklistItem
from core.execution.reasoning_gateway import ReasoningGateway, ReasoningRequest


@dataclass(frozen=True)
class ChecklistAtomizationRequest:
    project_id: str
    requirement_text: str


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
