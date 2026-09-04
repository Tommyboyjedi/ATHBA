"""Run the frozen PR29 Behavior Planner technical-decision qualification."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import subprocess
import time
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from core.development.behavior_contract_coordinator import (
    BEHAVIOR_PLANNER_CONTRACT_VERSION,
    BEHAVIOR_PLANNER_SCHEMA_SIGNATURE,
    BehaviorContractPlanner,
    ContractPlanningRequest,
    _contract_from_response,
)
from core.development.behavior_planner_qualification import (
    BehaviorPlannerQualificationCase,
    load_behavior_planner_qualification_v1,
)
from core.development.specification_domain import SourceRequirementClause
from core.execution.provider_reasoning_gateway import ProviderReasoningGateway
from core.execution.reasoning_gateway import ReasoningGateway, ReasoningRequest, ReasoningResult
from core.llm.contracts.provider import ProviderRetryPolicy
from core.llm.providers.openai_provider import OpenAIProvider


EXPECTED_HEAD = "44c74372639d76fb7637194014e389a41ed24cb4"
EXPECTED_CONTRACT_VERSION = "technical-decisions-v1"
EXPECTED_SCHEMA_SIGNATURE = "f601e38508a568ddbad10037a3f512120c3f17b87bd9fa9f4074b7a670ce016a"
EXPECTED_CORPUS_SHA = "523dc088007cdcd10484daa7cb272fdbdab4a37a306a5369bbeac1ff676d85cb"
EXPECTED_CASE_SHA = {
    "BPQ-V1-A": "6a88d231bc489d24507b0b9a7abbc61bd6e13e418a0d65567490da25c72eea36",
    "BPQ-V1-B": "c46ce04d165b64d2459fdd821475289925496dc7541584230d60f4858ec9aa88",
    "BPQ-V1-C": "65fe74ab5a04edd6b3e1cecd6a93da5b2b05ad45d973b131f712c8a4678d78bd",
}
RUN_ORDER = ("A1", "B1", "C1", "A2", "B2", "C2", "A3", "B3", "C3")
PATHS = {
    "BPQ-V1-A": (["reservation_book.py"], ["tests/test_reservation_book.py"]),
    "BPQ-V1-B": (["signal_board.py"], ["tests/test_signal_board.py"]),
    "BPQ-V1-C": (["parcel_locker.py"], ["tests/test_parcel_locker.py"]),
}


@dataclass
class RecordedExchange:
    purpose: str
    project_id: str
    prompt: str
    started_at: str
    finished_at: str | None = None
    duration_seconds: float | None = None
    raw_provider_response: str | None = None
    provider: str | None = None
    model: str | None = None
    error: str | None = None


@dataclass
class RecordingGateway(ReasoningGateway):
    """Qualification-only observer that delegates production requests unchanged."""

    delegate: ReasoningGateway
    exchanges: list[RecordedExchange] = field(default_factory=list)

    async def reason(self, request: ReasoningRequest) -> ReasoningResult:
        started = datetime.now(UTC).isoformat()
        clock = time.perf_counter()
        exchange = RecordedExchange(
            purpose=request.purpose,
            project_id=request.project_id,
            prompt=request.prompt,
            started_at=started,
        )
        try:
            result = await self.delegate.reason(request)
        except Exception as error:
            exchange.error = f"{type(error).__name__}: {error}"
            exchange.finished_at = datetime.now(UTC).isoformat()
            exchange.duration_seconds = round(time.perf_counter() - clock, 6)
            self.exchanges.append(exchange)
            raise
        exchange.raw_provider_response = result.text
        exchange.provider = result.provider
        exchange.model = result.model
        exchange.finished_at = datetime.now(UTC).isoformat()
        exchange.duration_seconds = round(time.perf_counter() - clock, 6)
        self.exchanges.append(exchange)
        return result


def git_head() -> str:
    return subprocess.run(
        ["git", "rev-parse", "HEAD"],
        check=True,
        text=True,
        capture_output=True,
    ).stdout.strip()


def atomic_json(path: Path, payload: object) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def write_exchange(run_dir: Path, name: str, exchange: RecordedExchange | None) -> dict[str, object] | None:
    if exchange is None:
        return None
    prompt_path = run_dir / f"{name}-prompt.txt"
    prompt_path.write_text(exchange.prompt, encoding="utf-8")
    response_path: str | None = None
    if exchange.raw_provider_response is not None:
        raw_path = run_dir / f"{name}-raw-provider-response.txt"
        raw_path.write_text(exchange.raw_provider_response, encoding="utf-8")
        response_path = raw_path.name
    return {
        "prompt_path": prompt_path.name,
        "raw_provider_response_path": response_path,
        "purpose": exchange.purpose,
        "provider": exchange.provider,
        "model": exchange.model,
        "started_at": exchange.started_at,
        "finished_at": exchange.finished_at,
        "duration_seconds": exchange.duration_seconds,
        "error": exchange.error,
    }


def json_object_parse_status(text: str | None) -> bool:
    if text is None:
        return False
    try:
        return isinstance(json.loads(text), dict)
    except json.JSONDecodeError:
        return False


def event_by_purpose(events: list[RecordedExchange], purpose: str) -> RecordedExchange | None:
    return next((event for event in events if event.purpose == purpose), None)


def contract_summary(contract: object, component_name: str, requirement_text: str) -> dict[str, object]:
    payload = contract.to_dict()
    decisions = list(payload["technical_decisions"])
    requirements = list(payload["observable_requirements"])
    binding_map = {
        str(requirement["ref"]): list(requirement["technical_bindings"])
        for requirement in requirements
    }
    class_decisions = [
        decision
        for decision in decisions
        if decision["origin"] == "source_requirement"
        and str(decision["qualified_identifier"]).rsplit(".", 1)[-1] == component_name
        and isinstance(decision.get("source_excerpt"), str)
        and str(decision["source_excerpt"]) in requirement_text
    ]
    bound_refs = {
        str(binding["technical_ref"])
        for bindings in binding_map.values()
        for binding in bindings
    }
    class_measurement = {
        "represented": bool(class_decisions),
        "decisions": class_decisions,
        "bound_to_relevant_behaviors": all(
            str(decision["ref"]) in bound_refs for decision in class_decisions
        ),
    }
    planner_created = [
        {
            "ref": decision["ref"],
            "kind": decision["kind"],
            "qualified_identifier": decision["qualified_identifier"],
            "source_clause_refs": decision["source_clause_refs"],
            "bindings": [
                {"requirement_ref": requirement_ref, **binding}
                for requirement_ref, bindings in binding_map.items()
                for binding in bindings
                if binding["technical_ref"] == decision["ref"]
            ],
        }
        for decision in decisions
        if decision["origin"] == "behavior_planner"
    ]
    return {
        "contract": payload,
        "source_clause_count": len(payload["source_clauses"]),
        "behavior_requirement_count": len(requirements),
        "technical_decision_count": len(decisions),
        "technical_binding_count": sum(len(bindings) for bindings in binding_map.values()),
        "public_api": payload["public_api"],
        "technical_decisions": decisions,
        "bindings_by_requirement": binding_map,
        "source_class_decision": class_measurement,
        "planner_created_identifiers": planner_created,
    }


def frozen_identity() -> dict[str, object]:
    corpus = load_behavior_planner_qualification_v1()
    changed_paths = set(
        filter(
            None,
            subprocess.run(
                ["git", "diff", "--name-only", EXPECTED_HEAD, "HEAD"],
                check=True,
                text=True,
                capture_output=True,
            ).stdout.splitlines(),
        )
    )
    allowed_harness_paths = {
        "scripts/run_pr29_behavior_planner_technical_decision_qualification.py"
    }
    if changed_paths - allowed_harness_paths:
        raise RuntimeError(
            f"production source differs from frozen initial head: {sorted(changed_paths - allowed_harness_paths)}"
        )
    if BEHAVIOR_PLANNER_CONTRACT_VERSION != EXPECTED_CONTRACT_VERSION:
        raise RuntimeError("planner contract version differs from the frozen qualification identity")
    if BEHAVIOR_PLANNER_SCHEMA_SIGNATURE != EXPECTED_SCHEMA_SIGNATURE:
        raise RuntimeError("planner schema signature differs from the frozen qualification identity")
    if corpus.version != "BPQ-V1" or corpus.corpus_sha256 != EXPECTED_CORPUS_SHA:
        raise RuntimeError("BPQ corpus identity differs from the frozen qualification identity")
    actual_hashes = {case.fixture_id: case.requirement_text_sha256 for case in corpus.cases}
    if actual_hashes != EXPECTED_CASE_SHA:
        raise RuntimeError(f"BPQ case identities differ: {actual_hashes}")
    return {
        "initial_expected_head": EXPECTED_HEAD,
        "planner_contract_version": BEHAVIOR_PLANNER_CONTRACT_VERSION,
        "planner_schema_signature": BEHAVIOR_PLANNER_SCHEMA_SIGNATURE,
        "bpq_corpus_sha256": corpus.corpus_sha256,
        "bpq_case_sha256": actual_hashes,
        "fixture_path": "qualification_fixtures/behavior_planner_qualification_v1.json",
    }


def build_gateway() -> ProviderReasoningGateway:
    return ProviderReasoningGateway(
        provider=OpenAIProvider(
            policy=ProviderRetryPolicy(timeout=300.0, max_retries=1, backoff_factor=2.0)
        ),
        model=os.environ.get("ATHBA_REASONING_MODEL", "local-primary"),
        max_tokens=4096,
    )


async def readiness(base_gateway: ReasoningGateway) -> dict[str, object]:
    clock = time.perf_counter()
    result = await base_gateway.reason(
        ReasoningRequest(
            purpose="athba_behavior_planner_qualification_readiness",
            prompt="Reply READY.",
            project_id="pr29-behavior-planner-qualification",
        )
    )
    return {
        "model_ready": True,
        "duration_seconds": round(time.perf_counter() - clock, 6),
        "provider": result.provider,
        "model": result.model,
    }


def first_contract_validation(
    exchange: RecordedExchange | None,
    source_clauses: list[SourceRequirementClause] | None,
    case: BehaviorPlannerQualificationCase,
    production_paths: list[str],
    test_paths: list[str],
) -> tuple[bool, str | None]:
    if exchange is None or exchange.raw_provider_response is None or source_clauses is None:
        return False, None
    try:
        _contract_from_response(
            exchange.raw_provider_response,
            label="behavior contract",
            project_id=f"pr29-{case.fixture_id.lower()}",
            requirement_text=case.requirement_text,
            source_clauses=source_clauses,
            allowed_production_paths=production_paths,
            allowed_test_paths=test_paths,
        )
    except ValueError as error:
        return False, str(error)
    return True, None


async def run_case(
    run_label: str,
    case: BehaviorPlannerQualificationCase,
    gateway: RecordingGateway,
    identity: dict[str, object],
    output_root: Path,
) -> dict[str, object]:
    run_dir = output_root / run_label
    run_dir.mkdir(parents=True, exist_ok=False)
    start_index = len(gateway.exchanges)
    started_at = datetime.now(UTC).isoformat()
    clock = time.perf_counter()
    production_paths, test_paths = PATHS[case.fixture_id]
    record: dict[str, object] = {
        "run": run_label,
        "fixture_id": case.fixture_id,
        "component_name": case.component_name,
        "requirement_sha256": case.requirement_text_sha256,
        "corpus_sha256": identity["bpq_corpus_sha256"],
        "athba_head": git_head(),
        "planner_contract_version": identity["planner_contract_version"],
        "planner_schema_signature": identity["planner_schema_signature"],
        "started_at": started_at,
        "production_paths": production_paths,
        "test_paths": test_paths,
    }
    source_clauses: list[SourceRequirementClause] | None = None
    contract: object | None = None
    final_error: str | None = None
    try:
        contract = await BehaviorContractPlanner(gateway).create_contract(
            ContractPlanningRequest(
                project_id=f"pr29-{case.fixture_id.lower()}",
                requirement_text=case.requirement_text,
                production_paths=production_paths,
                test_paths=test_paths,
            )
        )
    except Exception as error:
        final_error = f"{type(error).__name__}: {error}"
    events = gateway.exchanges[start_index:]
    source_exchange = event_by_purpose(events, "athba_source_requirement_clauses")
    behavior_exchange = event_by_purpose(events, "athba_behavior_contract")
    repair_exchange = event_by_purpose(events, "athba_behavior_contract_repair")
    if source_exchange is not None and source_exchange.raw_provider_response is not None:
        try:
            payload = json.loads(source_exchange.raw_provider_response)
            raw_clauses = payload.get("clauses") if isinstance(payload, dict) else None
            if isinstance(raw_clauses, list):
                source_clauses = [SourceRequirementClause.from_dict(dict(item)) for item in raw_clauses]
                atomic_json(run_dir / "parsed-source-clauses.json", [item.to_dict() for item in source_clauses])
        except (ValueError, TypeError, json.JSONDecodeError):
            source_clauses = None
    first_valid, first_validation_error = first_contract_validation(
        behavior_exchange, source_clauses, case, production_paths, test_paths
    )
    record.update(
        {
            "source_clause_exchange": write_exchange(run_dir, "source-clause", source_exchange),
            "behavior_planner_first_exchange": write_exchange(run_dir, "behavior-planner-first", behavior_exchange),
            "repair_exchange": write_exchange(run_dir, "behavior-planner-repair", repair_exchange),
            "source_clauses_parsed": None if source_clauses is None else [item.to_dict() for item in source_clauses],
            "first_response_json_object": json_object_parse_status(
                None if behavior_exchange is None else behavior_exchange.raw_provider_response
            ),
            "first_response_valid": first_valid,
            "repair_used": repair_exchange is not None,
            "first_validation_error": first_validation_error,
            "final_contract_accepted": contract is not None,
            "final_validation_error": final_error,
            "duration_seconds": round(time.perf_counter() - clock, 6),
            "finished_at": datetime.now(UTC).isoformat(),
            "model_execution_provenance": {
                "provider": None if behavior_exchange is None else behavior_exchange.provider,
                "model": None if behavior_exchange is None else behavior_exchange.model,
            },
        }
    )
    if contract is not None:
        summary = contract_summary(contract, case.component_name, case.requirement_text)
        record.update(summary)
        atomic_json(run_dir / "final-accepted-behavior-contract.json", summary["contract"])
    atomic_json(run_dir / "run-record.json", record)
    return record


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--verify-only", action="store_true")
    return parser.parse_args()


async def main() -> None:
    args = parse_args()
    identity = frozen_identity()
    if args.verify_only:
        print(json.dumps({"verify_only": "PASS", **identity}, sort_keys=True))
        return
    if args.output_dir is None:
        raise SystemExit("--output-dir is required for a live qualification")
    if args.output_dir.exists():
        raise SystemExit(f"output directory already exists: {args.output_dir}")
    args.output_dir.mkdir(parents=True, exist_ok=False)
    identity["qualification_frozen_head"] = git_head()
    atomic_json(args.output_dir / "frozen-identity.json", identity)
    base_gateway = build_gateway()
    try:
        readiness_record = await readiness(base_gateway)
    except Exception as error:
        atomic_json(
            args.output_dir / "manifest.json",
            {**identity, "model_ready": False, "readiness_error": f"{type(error).__name__}: {error}", "runs": []},
        )
        print("MODEL_READY=NO")
        return
    gateway = RecordingGateway(base_gateway)
    corpus = load_behavior_planner_qualification_v1()
    cases = {case.fixture_id: case for case in corpus.cases}
    runs: list[dict[str, object]] = []
    for run_label in RUN_ORDER:
        fixture_id = f"BPQ-V1-{run_label[0]}"
        runs.append(await run_case(run_label, cases[fixture_id], gateway, identity, args.output_dir))
        atomic_json(args.output_dir / "manifest.json", {**identity, "readiness": readiness_record, "runs": runs})
        print(f"{run_label}_FINAL_ACCEPTED={'YES' if runs[-1]['final_contract_accepted'] else 'NO'}")
    atomic_json(args.output_dir / "manifest.json", {**identity, "readiness": readiness_record, "runs": runs})
    print(f"EVIDENCE_ROOT={args.output_dir}")


if __name__ == "__main__":
    asyncio.run(main())
