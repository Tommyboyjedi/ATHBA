"""Run the durable PR23 strict-TDD feature controller.

Exit codes: 0 completed or controlled checkpoint; 2 blocked; 3 stalled;
4 transition limit; 5 recovery required; 6 invalid CLI input/configuration.
"""
from __future__ import annotations

import argparse
import asyncio
from dataclasses import dataclass
from enum import IntEnum
import json
from pathlib import Path
from typing import NoReturn, Sequence

from core.development.strict_tdd_live_run_composition import (
    StrictTddLiveRunCompositionFactory,
    StrictTddLiveRunCompositionRequest,
    StrictTddLiveRunConfiguration,
)
from core.development.strict_tdd_run_controller import StrictTddReceiptDeliveryError
from core.development.strict_tdd_run_domain import (
    StrictTddRunControllerConfig,
    StrictTddRunMode,
    StrictTddRunRequest,
    StrictTddRunResult,
    StrictTddRunStatus,
)
from core.development.strict_tdd_transition_provenance import StrictTddCheckpoint


class StrictTddRunnerExitCode(IntEnum):
    SUCCESS = 0
    BLOCKED = 2
    STALLED = 3
    TRANSITION_LIMIT_REACHED = 4
    RECOVERY_REQUIRED = 5
    INVALID_INPUT = 6
    RECEIPT_DELIVERY_FAILED = 7


@dataclass(frozen=True)
class StrictTddCliInput:
    mode: StrictTddRunMode
    run_id: str
    project_id: str
    requirement: str
    language: str
    test_framework: str
    production_paths: tuple[str, ...]
    test_paths: tuple[str, ...]
    state_root: Path
    evidence_root: Path
    checkpoint: StrictTddCheckpoint | None


class StrictTddArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:
        raise ValueError(message)


def parser() -> argparse.ArgumentParser:
    value = StrictTddArgumentParser(description=__doc__)
    commands = value.add_subparsers(dest="command", required=True)
    for command in ("start", "resume"):
        subparser = commands.add_parser(command)
        subparser.add_argument("--run-id", required=True)
        subparser.add_argument("--project-id", required=True)
        requirements = subparser.add_mutually_exclusive_group(required=True)
        requirements.add_argument("--requirement")
        requirements.add_argument("--requirement-file", type=Path)
        subparser.add_argument("--language", required=True, choices=("python",))
        subparser.add_argument("--test-framework", required=True, choices=("pytest",))
        subparser.add_argument("--production-path", action="append", required=True)
        subparser.add_argument("--test-path", action="append", required=True)
        subparser.add_argument("--state-root", type=Path, required=True)
        subparser.add_argument("--evidence-root", type=Path, required=True)
        subparser.add_argument(
            "--stop-after",
            choices=tuple(item.value for item in StrictTddCheckpoint),
        )
    return value


def parse(arguments: Sequence[str] | None = None) -> StrictTddCliInput:
    values = parser().parse_args(arguments)
    requirement = values.requirement
    if values.requirement_file is not None:
        requirement = values.requirement_file.read_text(encoding="utf-8")
    if requirement is None or not requirement.strip():
        raise ValueError("requirement must be non-empty")
    return StrictTddCliInput(
        StrictTddRunMode(values.command),
        values.run_id,
        values.project_id,
        requirement,
        values.language,
        values.test_framework,
        tuple(values.production_path),
        tuple(values.test_path),
        values.state_root,
        values.evidence_root,
        None if values.stop_after is None else StrictTddCheckpoint(values.stop_after),
    )


async def execute(
    input_value: StrictTddCliInput,
    factory: StrictTddLiveRunCompositionFactory,
) -> StrictTddRunResult:
    composition = factory.build(
        StrictTddLiveRunCompositionRequest(
            StrictTddLiveRunConfiguration(
                input_value.state_root,
                input_value.evidence_root,
                input_value.state_root / "projects" / input_value.project_id / "repository",
                input_value.project_id,
            )
        )
    )
    request = StrictTddRunRequest(
        input_value.run_id,
        input_value.project_id,
        input_value.requirement,
        input_value.language,
        input_value.test_framework,
        input_value.production_paths,
        input_value.test_paths,
        input_value.state_root.name,
        input_value.evidence_root.name,
        input_value.mode,
        input_value.checkpoint,
        composition.athba_revision,
        composition.rack_ai_revision,
        StrictTddRunControllerConfig(100),
    )
    if input_value.mode == StrictTddRunMode.START:
        return await composition.controller.start(request)
    return await composition.controller.resume(request)


def result_summary(result: StrictTddRunResult) -> dict[str, object]:
    path = result.last_transition_path
    return {
        "run_id": result.run_id,
        "project_id": result.project_id,
        "status": result.status.value,
        "checkpoint_reached": (
            None if result.reached_checkpoint is None else result.reached_checkpoint.value
        ),
        "canonical_ref": result.canonical_ref,
        "canonical_revision": result.canonical_sha,
        "working_ref": result.working_ref,
        "working_revision": result.working_sha,
        "last_transition": None if path is None else {
            "feature": path.feature_kind.value,
            "scenario": None if path.scenario_kind is None else path.scenario_kind.value,
            "microcycle": (
                None if path.microcycle_kind is None else path.microcycle_kind.value
            ),
        },
        "last_event_id": result.last_lifecycle_event_id,
        "blocked_reason": result.reason,
        "structured_report_path": result.structured_report_path,
        "markdown_report_path": result.markdown_report_path,
    }


def exit_code(result: StrictTddRunResult) -> StrictTddRunnerExitCode:
    values = {
        StrictTddRunStatus.BLOCKED: StrictTddRunnerExitCode.BLOCKED,
        StrictTddRunStatus.STALLED: StrictTddRunnerExitCode.STALLED,
        StrictTddRunStatus.TRANSITION_LIMIT_REACHED: (
            StrictTddRunnerExitCode.TRANSITION_LIMIT_REACHED
        ),
        StrictTddRunStatus.RECOVERY_REQUIRED: StrictTddRunnerExitCode.RECOVERY_REQUIRED,
    }
    return values.get(result.status, StrictTddRunnerExitCode.SUCCESS)


def main(
    arguments: Sequence[str] | None = None,
    factory: StrictTddLiveRunCompositionFactory | None = None,
) -> int:
    try:
        result = asyncio.run(
            execute(parse(arguments), factory or StrictTddLiveRunCompositionFactory())
        )
    except StrictTddReceiptDeliveryError as error:
        print(json.dumps({"status": "receipt_delivery_failed", "error": str(error)}, sort_keys=True))
        return int(StrictTddRunnerExitCode.RECEIPT_DELIVERY_FAILED)
    except (OSError, ValueError) as error:
        print(json.dumps({"status": "invalid_input", "error": str(error)}, sort_keys=True))
        return int(StrictTddRunnerExitCode.INVALID_INPUT)
    print(json.dumps(result_summary(result), sort_keys=True))
    return int(exit_code(result))


if __name__ == "__main__":
    raise SystemExit(main())
