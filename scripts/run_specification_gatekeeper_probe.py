"""Run three independent live Specification Gatekeeper atomization probes."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from core.development.specification_gatekeeper import (
    ChecklistAtomizationRequest,
    SpecificationChecklistPlanner,
    _checklist_prompt,
)
from core.execution.provider_reasoning_gateway import ProviderReasoningGateway
from core.execution.reasoning_gateway import ReasoningGateway, ReasoningRequest, ReasoningResult
from core.llm.providers.openai_provider import OpenAIProvider


PROJECT_ID = "specification-gatekeeper-atomization-probe"
REQUIREMENT = """Build a small in-memory `ReservationBook` for reservable resources.

A resource has a unique id and a positive integer capacity.

Clients can add resources, create uniquely identified reservations for a number of units on a resource, cancel reservations, and query remaining availability.

Reject duplicate resource ids, duplicate reservation ids, reservations for unknown resources, cancellation of unknown reservations, zero or negative quantities, and reservations exceeding remaining capacity.

Failed operations must not corrupt existing state.

Cancelling a reservation restores that capacity.

The implementation must be in-memory only, dependency-free, small, direct, readable Python 3.14, suitable for pytest, and free of unnecessary abstractions."""


@dataclass
class RecordingGateway(ReasoningGateway):
    """Capture the real request/result while delegating reasoning unchanged."""

    delegate: ReasoningGateway
    requests: list[ReasoningRequest] = field(default_factory=list)
    results: list[ReasoningResult] = field(default_factory=list)

    async def reason(self, request: ReasoningRequest) -> ReasoningResult:
        self.requests.append(request)
        result = await self.delegate.reason(request)
        self.results.append(result)
        return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        help="Optional durable JSON evidence path. Defaults under state/.",
    )
    return parser.parse_args()


def default_output_path() -> Path:
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    return Path("state") / f"specification-gatekeeper-probe-{timestamp}.json"


def structural_summary(items: list[dict[str, object]]) -> dict[str, object]:
    refs = [str(item["ref"]) for item in items]
    valid_kinds = {"behavior", "validation", "invariant", "constraint", "quality"}
    return {
        "item_count": len(items),
        "duplicate_refs": sorted({ref for ref in refs if refs.count(ref) > 1}),
        "invalid_kinds": sorted({str(item["kind"]) for item in items if item["kind"] not in valid_kinds}),
        "invalid_evidence_kinds": [],
    }


def raw_items(raw_output: str | None) -> list[dict[str, object]]:
    if raw_output is None:
        return []
    try:
        payload = json.loads(raw_output)
    except json.JSONDecodeError:
        return []
    items = payload.get("items") if isinstance(payload, dict) else None
    if not isinstance(items, list) or not all(isinstance(item, dict) for item in items):
        return []
    return [dict(item) for item in items]


async def run_probe() -> dict[str, object]:
    model = os.environ.get("ATHBA_REASONING_MODEL", "local-primary")
    live_gateway = ProviderReasoningGateway(
        provider=OpenAIProvider(timeout=300, max_retries=1),
        model=model,
        max_tokens=4096,
    )
    recording_gateway = RecordingGateway(live_gateway)
    planner = SpecificationChecklistPlanner(recording_gateway)
    prompt = _checklist_prompt(project_id=PROJECT_ID, requirement_text=REQUIREMENT)
    print("=== EXACT GATEKEEPER PROMPT ===")
    print(prompt)

    runs: list[dict[str, object]] = []
    for number in range(1, 4):
        request_count = len(recording_gateway.requests)
        result_count = len(recording_gateway.results)
        try:
            checklist = await planner.create_checklist(
                ChecklistAtomizationRequest(project_id=PROJECT_ID, requirement_text=REQUIREMENT)
            )
            raw_output = recording_gateway.results[result_count].text
            items = [item.to_dict() for item in checklist.items]
            run = {
                "run": number,
                "strict_parse": "passed",
                "raw_model_output": raw_output,
                "items": items,
                "structural": structural_summary(items),
            }
        except Exception as error:  # The raw result is still useful if parsing rejected it.
            raw_output = None
            if len(recording_gateway.results) > result_count:
                raw_output = recording_gateway.results[result_count].text
            run = {
                "run": number,
                "strict_parse": "failed",
                "error": f"{type(error).__name__}: {error}",
                "raw_model_output": raw_output,
                "items": [],
                "raw_items": raw_items(raw_output),
                "structural": structural_summary(raw_items(raw_output)),
            }
        if len(recording_gateway.requests) != request_count + 1:
            raise RuntimeError("each probe run must make exactly one live Gatekeeper request")
        runs.append(run)
        print(f"\n=== RUN {number}: RAW MODEL OUTPUT ===")
        print(run["raw_model_output"])
        print(f"=== RUN {number}: STRUCTURED CHECKLIST ===")
        print(f"STRICT_PARSE: {run['strict_parse']}")
        if "error" in run:
            print(f"PARSE_ERROR: {run['error']}")
        print("REF | KIND | TEXT")
        display_items = run["items"] or run.get("raw_items", [])
        for item in display_items:
            print(f"{item['ref']} | {item['kind']} | {item['text']}")
        print(f"STRUCTURAL: {json.dumps(run['structural'], sort_keys=True)}")

    return {
        "project_id": PROJECT_ID,
        "requirement": REQUIREMENT,
        "exact_prompt": prompt,
        "runs": runs,
    }


async def main() -> None:
    args = parse_args()
    evidence = await run_probe()
    output = args.output or default_output_path()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(evidence, indent=2, sort_keys=True), encoding="utf-8")
    print(f"\nEVIDENCE_FILE: {output}")


if __name__ == "__main__":
    asyncio.run(main())
