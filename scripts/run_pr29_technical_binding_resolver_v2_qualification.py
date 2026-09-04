"""Frozen live qualification for TechnicalBindingResolver v2."""
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

from core.development.technical_binding_resolver_v2 import (
    TechnicalBindingResolverV2,
    stage1_schema_signature,
    stage2_schema_signature,
)
from core.development.technical_binding_resolver_v2_qualification import (
    CONTRACT_VERSION,
    EXPECTED,
    LOCAL_REASONING_CONFIGURATION,
    MATRIX,
    fixtures,
    signature,
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
        value = await asyncio.to_thread(
            self.provider.invoke, ProviderRequest(request.prompt, self.model, 0.0, 2048)
        )
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


def write(path: Path, value: object) -> None:
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
        "format_repair_count": trace.repair_count,
        "provenance": [
            {"provider": event["provider"], "model": event["model"], "duration_seconds": event["duration_seconds"]}
            for event in events
        ],
    }


async def run(args: argparse.Namespace) -> int:
    root = Path(args.repository_root).resolve()
    model = os.environ.get("ATHBA_REASONING_MODEL", "local-primary")
    if model != "local-primary":
        raise SystemExit("v2 requires local-primary")
    evidence = Path(args.evidence_root or root / "evidence" / f"technical-binding-resolver-v2-{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}")
    evidence.mkdir(parents=True, exist_ok=False)
    frozen = head(root)
    gateway = Gateway(model, args.timeout_seconds)
    write(evidence / "contract.json", {
        "contract_version": CONTRACT_VERSION,
        "frozen_head": frozen,
        "stage1_schema_signature": stage1_schema_signature(),
        "stage2_schema_signature": stage2_schema_signature(),
        "contract_signature": signature(root, model),
        "configuration": LOCAL_REASONING_CONFIGURATION,
        "matrix": MATRIX,
        "expected": EXPECTED,
    })
    try:
        ready = await gateway.reason(ReasoningRequest("athba_technical_binding_resolver_v2_readiness", "Return exactly READY.", "technical-binding-resolver-v2-readiness"))
        ready_ok = ready.text.strip() == "READY" and ready.model == "local-primary"
        write(evidence / "readiness.json", {"model_ready": ready_ok, "event": gateway.events[-1]})
    except Exception as error:
        write(evidence / "readiness.json", {"model_ready": False, "error": str(error)})
        return 2
    if not ready_ok:
        return 2

    records: list[dict[str, Any]] = []
    cases = fixtures(root)
    for run_id in MATRIX:
        case = cases[run_id.split("-")[0]]
        before = len(gateway.events)
        started = monotonic()
        result = await TechnicalBindingResolverV2(gateway).resolve(case.request)
        events = gateway.events[before:]
        stage1_events = events[: 1 + result.stage1_trace.repair_count]
        stage2_events = events[len(stage1_events) :]
        expected_status, expected_refs = EXPECTED[case.fixture_id]
        actual_status = result.stage1.status.value
        selected_refs = () if result.stage2 is None else result.stage2.selected_technical_refs
        expected_stage2 = expected_status == "binding_required"
        stage2_reached = result.stage2_trace is not None
        mechanical = actual_status != "protocol_failure" and stage2_reached == expected_stage2 and (not stage2_reached or result.stage2 is not None)
        semantic = actual_status == expected_status and selected_refs == expected_refs and stage2_reached == expected_stage2
        stage2_record = None if result.stage2_trace is None else {
            "behavior_ref": None if result.stage2 is None else result.stage2.behavior_ref,
            "selected_technical_refs": None if result.stage2 is None else list(result.stage2.selected_technical_refs),
            "rationale": None if result.stage2 is None else result.stage2.rationale,
            "evidence_refs": None if result.stage2 is None else list(result.stage2.evidence_refs),
            "trace": trace_record(result.stage2_trace, stage2_events),
        }
        record = {
            "run_id": run_id,
            "fixture_id": case.fixture_id,
            "frozen_head": frozen,
            "contract_version": CONTRACT_VERSION,
            "stage1_schema_signature": stage1_schema_signature(),
            "stage2_schema_signature": stage2_schema_signature(),
            "stage1": {
                "status": actual_status,
                "behavior_ref": result.stage1.behavior_ref,
                "rationale": result.stage1.rationale,
                "evidence_refs": list(result.stage1.evidence_refs),
                "trace": trace_record(result.stage1_trace, stage1_events),
            },
            "stage2": stage2_record,
            "mechanical_pass": mechanical,
            "semantic_pass": semantic,
            "duration_seconds": round(monotonic() - started, 6),
        }
        write(evidence / f"{run_id}.json", record)
        records.append(record)
        print(run_id, mechanical, semantic, actual_status, flush=True)

    summary: dict[str, Any] = {
        "model_ready": True,
        "runs_completed": len(records),
        "mechanical_pass_count": sum(record["mechanical_pass"] for record in records),
        "semantic_pass_count": sum(record["semantic_pass"] for record in records),
        "stage1_format_repair_count": sum(record["stage1"]["trace"]["format_repair_count"] for record in records),
        "stage2_format_repair_count": sum(0 if record["stage2"] is None else record["stage2"]["trace"]["format_repair_count"] for record in records),
        "stage2_call_count": sum(record["stage2"] is not None for record in records),
    }
    summary["qualified"] = summary["mechanical_pass_count"] == 12 and summary["semantic_pass_count"] == 12
    summary["failure_pattern"] = "; ".join(record["run_id"] for record in records if not record["mechanical_pass"] or not record["semantic_pass"]) or "NONE"
    write(evidence / "summary.json", summary)
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
