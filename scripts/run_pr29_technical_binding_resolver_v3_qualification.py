"""Frozen live qualification for TechnicalBindingResolver v3."""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from time import monotonic
from typing import Any

from core.development.technical_binding_resolver_v3 import (
    TechnicalBindingResolverV3,
    selection_schema_signature,
)
from core.development.technical_binding_resolver_v3_qualification import (
    CONTRACT_VERSION,
    LOCAL_REASONING_CONFIGURATION,
    MATRIX,
    expected_results,
    load_fixtures,
    qualification_contract_signature,
)
from core.execution.reasoning_gateway import ReasoningRequest, ReasoningResult
from core.llm.contracts.provider import ProviderRequest, ProviderRetryPolicy
from core.llm.providers.openai_provider import OpenAIProvider


class Gateway:
    def __init__(self, model: str, timeout: float) -> None:
        self.model = model
        self.provider = OpenAIProvider(ProviderRetryPolicy(timeout, 0, 1.0))
        self.events: list[dict[str, Any]] = []

    async def reason(self, request: ReasoningRequest) -> ReasoningResult:
        started = monotonic()
        value = await asyncio.to_thread(self.provider.invoke, ProviderRequest(request.prompt, self.model, 0.0, 2048))
        raw = dict(value.raw)
        model = str(raw.get("model") or self.model)
        provider = raw.get("provider")
        provider_name = provider if isinstance(provider, str) else None
        event = {
            "purpose": request.purpose,
            "exact_prompt": request.prompt,
            "raw_provider_response": raw,
            "response_text": value.text,
            "model": model,
            "provider": provider_name,
            "duration_seconds": round(monotonic() - started, 6),
        }
        self.events.append(event)
        return ReasoningResult(value.text, provider_name, model)


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def head(root: Path) -> str:
    return subprocess.check_output(("git", "-C", str(root), "rev-parse", "HEAD"), text=True).strip()


def trace_record(trace, events: list[dict[str, Any]]) -> dict[str, object]:
    return {
        "prompt": trace.request.prompt,
        "raw_response": events[0]["raw_provider_response"] if events else None,
        "response_text": trace.response.text if trace.response else None,
        "repair_prompt": trace.repair_request.prompt if trace.repair_request else None,
        "repair_raw_response": events[1]["raw_provider_response"] if len(events) > 1 else None,
        "repair_response_text": trace.repair_response.text if trace.repair_response else None,
        "validation": trace.validation_error,
        "format_repair_count": trace.format_repair_count,
        "provenance": [
            {"provider": event["provider"], "model": event["model"], "duration_seconds": event["duration_seconds"]}
            for event in events
        ],
    }


async def run(args: argparse.Namespace) -> int:
    root = Path(args.repository_root).resolve()
    model = os.environ.get("ATHBA_REASONING_MODEL", "local-primary")
    if model != "local-primary":
        raise SystemExit("v3 requires local-primary")
    evidence = Path(args.evidence_root or root / "evidence" / f"technical-binding-resolver-v3-{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}")
    evidence.mkdir(parents=True, exist_ok=False)
    frozen_head = head(root)
    gateway = Gateway(model, args.timeout_seconds)
    expected = expected_results(root)
    write_json(evidence / "contract.json", {
        "contract_version": CONTRACT_VERSION,
        "frozen_head": frozen_head,
        "schema_signature": selection_schema_signature(),
        "contract_signature": qualification_contract_signature(root, model),
        "configuration": LOCAL_REASONING_CONFIGURATION,
        "matrix": MATRIX,
        "expected": expected,
    })
    try:
        readiness = await gateway.reason(ReasoningRequest("athba_technical_binding_subset_selection_v3_readiness", "Return exactly READY.", "technical-binding-resolver-v3-readiness"))
        model_ready = readiness.text.strip() == "READY" and readiness.model == "local-primary"
        write_json(evidence / "readiness.json", {"model_ready": model_ready, "event": gateway.events[-1]})
    except Exception as error:
        write_json(evidence / "readiness.json", {"model_ready": False, "error": str(error)})
        return 2
    if not model_ready:
        return 2

    records: list[dict[str, Any]] = []
    fixtures = load_fixtures(root)
    for run_id in MATRIX:
        fixture = fixtures[run_id.split("-")[0]]
        before = len(gateway.events)
        started = monotonic()
        resolution = await TechnicalBindingResolverV3(gateway).resolve(fixture.request)
        events = gateway.events[before:]
        selected_refs = () if resolution.selection is None else resolution.selection.selected_refs
        mechanical_pass = resolution.selection is not None
        semantic_pass = mechanical_pass and selected_refs == fixture.expected_selected_refs
        record = {
            "run_id": run_id,
            "fixture_id": fixture.fixture_id,
            "frozen_head": frozen_head,
            "contract_version": CONTRACT_VERSION,
            "schema_signature": selection_schema_signature(),
            "selection": None if resolution.selection is None else {
                "behavior_ref": resolution.selection.behavior_ref,
                "selected_refs": list(resolution.selection.selected_refs),
            },
            "trace": trace_record(resolution.trace, events),
            "mechanical_pass": mechanical_pass,
            "semantic_pass": semantic_pass,
            "duration_seconds": round(monotonic() - started, 6),
        }
        write_json(evidence / f"{run_id}.json", record)
        records.append(record)
        print(run_id, mechanical_pass, semantic_pass, list(selected_refs), flush=True)

    summary: dict[str, Any] = {
        "model_ready": True,
        "runs_completed": len(records),
        "mechanical_pass_count": sum(record["mechanical_pass"] for record in records),
        "semantic_pass_count": sum(record["semantic_pass"] for record in records),
        "format_repair_count": sum(record["trace"]["format_repair_count"] for record in records),
    }
    summary["qualified"] = summary["mechanical_pass_count"] == 12 and summary["semantic_pass_count"] == 12
    summary["failure_pattern"] = "; ".join(record["run_id"] for record in records if not record["mechanical_pass"] or not record["semantic_pass"]) or "NONE"
    write_json(evidence / "summary.json", summary)
    print("EVIDENCE_ROOT=" + str(evidence))
    return 0 if summary["qualified"] else 2


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository-root", default=".")
    parser.add_argument("--evidence-root")
    parser.add_argument("--timeout-seconds", type=float, default=180.0)
    return asyncio.run(run(parser.parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
