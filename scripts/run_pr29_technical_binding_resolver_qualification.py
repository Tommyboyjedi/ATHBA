"""Frozen live qualification runner for TechnicalBindingResolver v1."""
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

from core.development.technical_binding_resolver import (
    TechnicalBindingResolutionStatus, TechnicalBindingResolver,
    output_schema, output_schema_signature,
)
from core.development.technical_binding_resolver_qualification import (
    CONTRACT_VERSION, LOCAL_REASONING_CONFIGURATION, QUALIFICATION_MATRIX,
    fixture_bytes, load_fixtures, qualification_contract_signature,
)
from core.execution.reasoning_gateway import ReasoningRequest, ReasoningResult
from core.llm.contracts.provider import ProviderRequest, ProviderRetryPolicy
from core.llm.providers.openai_provider import OpenAIProvider

class EvidenceGateway:
    """Harness-only evidence wrapper over ATHBA's normal provider-neutral path."""
    def __init__(self, model: str, timeout: float):
        self.model = model
        self.provider = OpenAIProvider(ProviderRetryPolicy(timeout=timeout, max_retries=0, backoff_factor=1.0))
        self.exchanges: list[dict[str, Any]] = []
    async def reason(self, request: ReasoningRequest) -> ReasoningResult:
        started = monotonic()
        normalized = await asyncio.to_thread(self.provider.invoke, ProviderRequest(request.prompt, self.model, 0.0, 2048))
        raw = dict(normalized.raw)
        provider = str(raw["provider"]) if raw.get("provider") is not None else None
        model = str(raw["model"]) if raw.get("model") is not None else self.model
        self.exchanges.append({
            "purpose": request.purpose, "project_id": request.project_id, "exact_prompt": request.prompt,
            "raw_provider_response": raw, "response_text": normalized.text,
            "provider": provider, "model": model, "duration_seconds": round(monotonic() - started, 6),
        })
        return ReasoningResult(normalized.text, provider, model)

def git_head(root: Path) -> str:
    return subprocess.check_output(("git", "-C", str(root), "rev-parse", "HEAD"), text=True).strip()

def json_write(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")

def resolution_payload(trace) -> dict[str, object]:
    result = trace.resolution
    return {
        "status": result.status.value, "behavior_ref": result.behavior_ref,
        "bindings": [{"technical_ref": item.technical_ref, "role": item.role.value} for item in result.bindings],
        "rationale": result.rationale, "evidence_refs": list(result.evidence_refs),
    }

def provenance(exchange: dict[str, Any] | None) -> dict[str, Any] | None:
    if exchange is None:
        return None
    return {key: exchange[key] for key in ("provider", "model", "duration_seconds")}

async def run(arguments: argparse.Namespace) -> int:
    root = Path(arguments.repository_root).resolve()
    model = os.environ.get("ATHBA_REASONING_MODEL", "local-primary")
    if model != "local-primary":
        raise SystemExit("technical binding resolver qualification requires configured local-primary")
    evidence_root = Path(arguments.evidence_root).resolve() if arguments.evidence_root else root / "evidence" / f"technical-binding-resolver-v1-{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}"
    evidence_root.mkdir(parents=True, exist_ok=False)
    head = git_head(root)
    fixtures = load_fixtures(root)
    contract_signature = qualification_contract_signature(root, model)
    frozen = {
        "resolver_contract_version": CONTRACT_VERSION, "resolver_schema_signature": output_schema_signature(),
        "qualification_contract_signature": contract_signature, "athba_head": head,
        "fixture_sha256": __import__("hashlib").sha256(fixture_bytes(root)).hexdigest(),
        "prompt_template": "core.development.technical_binding_resolver._semantic_request",
        "output_schema": output_schema(), "local_reasoning_configuration": LOCAL_REASONING_CONFIGURATION,
        "configured_model": model, "configured_api_base": os.environ.get("OPENAI_API_BASE"),
        "qualification_matrix": QUALIFICATION_MATRIX,
        "mechanical_threshold": "12/12 deterministically valid non-protocol terminal results",
        "semantic_threshold": "every run must exactly match its frozen fixture expected status and bindings",
    }
    json_write(evidence_root / "qualification-contract.json", frozen)
    gateway = EvidenceGateway(model, arguments.timeout_seconds)
    readiness_request = ReasoningRequest("athba_technical_binding_resolver_readiness", "Return exactly READY.", "technical-binding-resolver-readiness")
    try:
        readiness = await gateway.reason(readiness_request)
        ready_exchange = gateway.exchanges[-1]
        ready = readiness.text.strip() == "READY" and ready_exchange["model"] == "local-primary"
        json_write(evidence_root / "readiness.json", {"model_ready": ready, "exchange": ready_exchange, "configured_model": model})
    except Exception as error:
        json_write(evidence_root / "readiness.json", {"model_ready": False, "error": str(error), "configured_model": model})
        json_write(evidence_root / "qualification-summary.json", {"model_ready": False, "runs_completed": 0, "qualified": False, "failure_pattern": "MODEL_NOT_READY"})
        return 2
    if not ready:
        json_write(evidence_root / "qualification-summary.json", {"model_ready": False, "runs_completed": 0, "qualified": False, "failure_pattern": "MODEL_NOT_READY"})
        return 2
    records: list[dict[str, Any]] = []
    for run_id in QUALIFICATION_MATRIX:
        fixture_id = run_id.split("-")[0]
        fixture = fixtures[fixture_id]
        before = len(gateway.exchanges)
        started = monotonic()
        trace = await TechnicalBindingResolver(gateway).resolve_with_trace(fixture.request)
        exchanges = gateway.exchanges[before:]
        actual = trace.resolution
        expected_pairs = {(binding.technical_ref, binding.role.value) for binding in fixture.expected.bindings}
        actual_pairs = {(binding.technical_ref, binding.role.value) for binding in actual.bindings}
        mechanical_pass = actual.status is not TechnicalBindingResolutionStatus.PROTOCOL_FAILURE
        semantic_pass = actual.status is fixture.expected.status and actual_pairs == expected_pairs
        record = {
            "run_id": run_id, "fixture_id": fixture_id, "resolver_contract_version": CONTRACT_VERSION,
            "resolver_schema_signature": output_schema_signature(), "athba_head": head,
            "exact_semantic_prompt": trace.semantic_request.prompt,
            "raw_provider_response": exchanges[0]["raw_provider_response"] if exchanges else None,
            "semantic_provider_response_text": trace.semantic_response.text if trace.semantic_response else None,
            "format_repair_prompt": trace.repair_request.prompt if trace.repair_request else None,
            "format_repair_raw_provider_response": exchanges[1]["raw_provider_response"] if len(exchanges) > 1 else None,
            "format_repair_response_text": trace.repair_response.text if trace.repair_response else None,
            "parsed_result": resolution_payload(trace), "deterministic_validation_outcome": "valid" if mechanical_pass else trace.validation_error,
            "selected_bindings": resolution_payload(trace)["bindings"], "rationale": actual.rationale,
            "evidence_refs": list(actual.evidence_refs), "duration_seconds": round(monotonic() - started, 6),
            "provider_model_provenance": {"semantic": provenance(exchanges[0] if exchanges else None), "format_repair": provenance(exchanges[1] if len(exchanges) > 1 else None)},
            "format_repair_count": trace.format_repair_count, "mechanical_pass": mechanical_pass, "semantic_pass": semantic_pass,
        }
        json_write(evidence_root / f"{run_id}.json", record)
        records.append(record)
        print(f"{run_id} mechanical={'PASS' if mechanical_pass else 'FAIL'} semantic={'PASS' if semantic_pass else 'FAIL'} status={actual.status.value}", flush=True)
    mechanical_count = sum(record["mechanical_pass"] for record in records)
    semantic_count = sum(record["semantic_pass"] for record in records)
    repair_count = sum(record["format_repair_count"] for record in records)
    qualified = len(records) == 12 and mechanical_count == 12 and semantic_count == 12
    failures = [f"{record['run_id']}:{record['parsed_result']['status']}" for record in records if not record["mechanical_pass"] or not record["semantic_pass"]]
    summary = {
        "model_ready": True, "runs_completed": len(records), "format_repair_count": repair_count,
        "mechanical_pass_count": mechanical_count, "semantic_pass_count": semantic_count,
        "qualified": qualified, "failure_pattern": "; ".join(failures) if failures else "NONE",
        "runs": [{"run_id": record["run_id"], "mechanical_pass": record["mechanical_pass"], "semantic_pass": record["semantic_pass"], "status": record["parsed_result"]["status"]} for record in records],
    }
    json_write(evidence_root / "qualification-summary.json", summary)
    print(f"EVIDENCE_ROOT={evidence_root}", flush=True)
    print(f"TECHNICAL_BINDING_RESOLVER_QUALIFIED={'YES' if qualified else 'NO'}", flush=True)
    return 0 if qualified else 2

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository-root", default=".")
    parser.add_argument("--evidence-root")
    parser.add_argument("--timeout-seconds", type=float, default=180.0)
    return asyncio.run(run(parser.parse_args()))

if __name__ == "__main__":
    raise SystemExit(main())
