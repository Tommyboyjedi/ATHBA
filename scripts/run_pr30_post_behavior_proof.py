"""Run one frozen disposable behavioral delivery through the real PR30 continuation.

The fixture is operator supplied and immutable once predeclared. This runner never
edits target code or changes assessor decisions to manufacture the positive path.
"""
from __future__ import annotations

import argparse
import asyncio
from dataclasses import asdict, dataclass
from enum import Enum
from hashlib import sha256
import json
from pathlib import Path
from subprocess import SubprocessError

from core.atomic_json_file import read_json_file, write_json_atomically
from core.development.post_behavior_composition import PostBehaviorCompositionFactory, PostBehaviorCompositionRequest
from core.development.post_behavior_domain import (
    MAX_PROMOTED_REFACTOR_PASSES, PostBehaviorOutcome, PostBehaviorPass, PostBehaviorPhase, PostBehaviorReason,
    PostBehaviorState, PostBehaviorStatus,
)
from core.development.post_behavior_evidence import PostBehaviorEvidenceStore
from core.development.post_behavior_git import PostBehaviorGit
from core.development.post_behavior_store import PostBehaviorStateCodec
from core.development.strict_tdd_live_run_composition import (
    StrictTddLiveRunComposition, StrictTddLiveRunCompositionFactory,
    StrictTddLiveRunCompositionRequest, StrictTddLiveRunConfiguration,
)
from core.development.python_pytest_preflight import PythonProbePreflightError
from core.development.strict_tdd_run_controller import StrictTddReceiptDeliveryError
from core.development.strict_tdd_run_domain import (
    StrictTddRunControllerConfig, StrictTddRunMode, StrictTddRunRequest, StrictTddRunStatus,
)
from core.execution.provider_reasoning_gateway import ProviderReasoningGateway
from core.filesystem_policy import resolve_identifier_path, validate_filesystem_identifier
from core.llm.contracts.provider import ProviderRetryPolicy
from core.llm.providers.openai_provider import OpenAIProvider

MAX_BEHAVIOR_TRANSITIONS = 1000
REASONING_TIMEOUT_SECONDS = 300.0
PROOF_SCHEMA = "pr30-disposable-proof/v1"
REQUIRED_CHAIN = (
    "Gatekeeper-approved behavior", "naming YES", "production/test exact rename",
    "accepted tests GREEN", "Gatekeeper YES", "naming NO", "refactor YES",
    "production-only refactor", "unchanged tests GREEN", "Gatekeeper YES",
    "refactor NO", "POST_BEHAVIOR_COMPLETE",
)


class ProofStatus(str, Enum):
    PASSED = "passed"
    NOT_OBSERVED = "proof_not_observed"
    BLOCKED = "blocked"


@dataclass(frozen=True)
class ProofInput:
    run_id: str
    project_id: str
    requirement_file: Path
    state_root: Path
    evidence_root: Path
    reasoning_model: str
    production_paths: tuple[str, ...]
    test_paths: tuple[str, ...]
    mode: StrictTddRunMode = StrictTddRunMode.START

    def __post_init__(self) -> None:
        validate_filesystem_identifier(self.run_id, "run id")
        validate_filesystem_identifier(self.project_id, "project id")
        if not self.reasoning_model or not self.production_paths or not self.test_paths:
            raise ValueError("proof requires fixed reasoning identity and explicit production/test paths")

    @property
    def proof_root(self) -> Path:
        return resolve_identifier_path(self.evidence_root.resolve(), self.run_id, "proof run id")


@dataclass(frozen=True)
class ProofScope:
    repository_root: Path
    production_paths: tuple[str, ...]
    test_paths: tuple[str, ...]


@dataclass(frozen=True)
class ProofReport:
    status: ProofStatus
    reason: str
    behavioral_baseline: str | None = None
    final_revision: str | None = None
    accepted_rename_revisions: tuple[str, ...] = ()
    accepted_refactor_revisions: tuple[str, ...] = ()


def predeclare(arguments: ProofInput, composition: StrictTddLiveRunComposition) -> str:
    requirement = arguments.requirement_file.read_text(encoding="utf-8")
    if not requirement.strip():
        raise ValueError("proof fixture requirement cannot be empty")
    plan = {
        "schema": PROOF_SCHEMA, "run_id": arguments.run_id, "project_id": arguments.project_id,
        "requirement_file": str(arguments.requirement_file.resolve()), "requirement_text": requirement,
        "requirement_sha256": sha256(requirement.encode()).hexdigest(),
        "state_root": str(arguments.state_root.resolve()), "evidence_root": str(arguments.evidence_root.resolve()),
        "reasoning_model": arguments.reasoning_model, "production_paths": list(arguments.production_paths),
        "test_paths": list(arguments.test_paths), "athba_revision": composition.athba_revision,
        "rack_ai_revision": composition.rack_ai_revision, "required_chain": list(REQUIRED_CHAIN),
        "max_behavior_transitions": MAX_BEHAVIOR_TRANSITIONS,
        "max_promoted_refactors": MAX_PROMOTED_REFACTOR_PASSES, "manual_target_edits_permitted": False,
    }
    path = arguments.proof_root / "predeclared.json"
    if path.exists():
        if read_json_file(path) != plan:
            raise ValueError("proof fixture, code identity or execution plan changed after predeclaration")
        if arguments.mode != StrictTddRunMode.RESUME:
            raise ValueError("proof already predeclared; resume its existing state instead of starting another proof")
    else:
        if arguments.mode == StrictTddRunMode.RESUME:
            raise ValueError("proof cannot resume without its immutable predeclaration")
        write_json_atomically(path, plan)
    return requirement


def observe(state: PostBehaviorState, scope: ProofScope) -> ProofReport:
    if state.status != PostBehaviorStatus.POST_BEHAVIOR_COMPLETE:
        return ProofReport(ProofStatus.BLOCKED, state.diagnostic or str(state.terminal_reason),
                           state.behaviorally_accepted_revision, state.current_post_behavior_revision)
    naming = tuple(item for item in state.passes if item.phase == PostBehaviorPhase.NAMING
                   and item.outcome == PostBehaviorOutcome.PROMOTED)
    refactoring = tuple(item for item in state.passes if item.phase == PostBehaviorPhase.REFACTORING
                        and item.outcome == PostBehaviorOutcome.PROMOTED)
    reason = "positive naming and refactoring work was not both observed"
    passed = bool(naming and refactoring)
    if state.terminal_reason != PostBehaviorReason.REFACTOR_NO_CHANGE:
        passed = False
        reason = "the positive proof requires an explicit final refactor NO"
    if passed:
        git = PostBehaviorGit(scope.repository_root)
        passed = all(_mutation_provenance(item) for item in (*naming, *refactoring))
        reason = "retained real workspace execution provenance is incomplete"
        if passed:
            naming_paths = [_changed_paths(git, item) for item in naming]
            refactor_paths = [_changed_paths(git, item) for item in refactoring]
            passed = (any(paths & set(scope.test_paths) and paths & set(scope.production_paths)
                          for paths in naming_paths)
                      and all(paths & set(scope.production_paths) and not paths & set(scope.test_paths)
                              for paths in refactor_paths))
            reason = "required production/test rename or unchanged-test refactor was not observed"
    return ProofReport(
        ProofStatus.PASSED if passed else ProofStatus.NOT_OBSERVED,
        "required positive chain observed with exact accepted revisions" if passed else reason,
        state.behaviorally_accepted_revision, state.current_post_behavior_revision,
        tuple(item.candidate.revision for item in naming if item.candidate and item.candidate.revision),
        tuple(item.candidate.revision for item in refactoring if item.candidate and item.candidate.revision))


def _changed_paths(git: PostBehaviorGit, change: PostBehaviorPass) -> set[str]:
    assert change.candidate is not None and change.candidate.revision is not None
    return set(git.command(("diff", "--name-only", change.base_revision, change.candidate.revision)).splitlines())


def _mutation_provenance(change: PostBehaviorPass) -> bool:
    assert change.candidate is not None
    for reference in change.candidate.evidence_refs:
        path = Path(reference)
        if not path.is_file():
            continue
        try:
            artifact = read_json_file(path)
            payload = artifact.get("payload", {})
            if not isinstance(payload, dict) or not isinstance(payload.get("identity"), dict):
                continue
            if (artifact.get("kind") == "workspace_result"
                    and payload.get("identity", {}).get("submission_id") == change.submission_id
                    and isinstance(payload.get("execution_provenance"), dict) and payload["execution_provenance"]
                    and (payload.get("candidate_revision") or payload.get("accepted_revision")) == change.candidate.revision):
                return True
        except (OSError, ValueError, TypeError):
            continue
    return False


async def execute(arguments: ProofInput) -> ProofReport:
    evidence = PostBehaviorEvidenceStore(arguments.proof_root)
    composition = StrictTddLiveRunCompositionFactory().build(StrictTddLiveRunCompositionRequest(
        StrictTddLiveRunConfiguration(arguments.state_root, arguments.evidence_root,
            arguments.state_root / "projects" / arguments.project_id / "repository",
            arguments.project_id, reasoning_model=arguments.reasoning_model,
            athba_repository_root=Path(__file__).resolve().parents[1])))
    requirement = predeclare(arguments, composition)
    request = StrictTddRunRequest(
        arguments.run_id, arguments.project_id, requirement, "python", "pytest",
        arguments.production_paths, arguments.test_paths, arguments.state_root.name,
        arguments.evidence_root.name, arguments.mode, None, composition.athba_revision,
        composition.rack_ai_revision, StrictTddRunControllerConfig(MAX_BEHAVIOR_TRANSITIONS))
    behavioral = await (composition.controller.start(request) if arguments.mode == StrictTddRunMode.START
                        else composition.controller.resume(request))
    evidence.record("behavioral_delivery_result", behavioral)
    if behavioral.status != StrictTddRunStatus.COMPLETED:
        report = ProofReport(ProofStatus.BLOCKED, behavioral.reason or behavioral.status.value,
                             final_revision=behavioral.canonical_sha)
        evidence.record("proof_result", report)
        return report
    provider = OpenAIProvider(policy=ProviderRetryPolicy(
        timeout=REASONING_TIMEOUT_SECONDS, max_retries=0, backoff_factor=1.0))
    gateway = ProviderReasoningGateway(provider, arguments.reasoning_model)
    lifecycle = PostBehaviorCompositionFactory().build(PostBehaviorCompositionRequest(
        arguments.state_root, arguments.project_id, gateway))
    state = await lifecycle.run(arguments.project_id)
    evidence.record("post_behavior_state", PostBehaviorStateCodec.encode(state))
    report = observe(state, ProofScope(
        arguments.state_root / "projects" / arguments.project_id / "repository",
        arguments.production_paths, arguments.test_paths))
    evidence.record("proof_result", report)
    return report


def parse() -> ProofInput:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--project-id", required=True)
    parser.add_argument("--requirement-file", type=Path, required=True)
    parser.add_argument("--state-root", type=Path, required=True)
    parser.add_argument("--evidence-root", type=Path, required=True)
    parser.add_argument("--reasoning-model", required=True)
    parser.add_argument("--production-path", action="append", required=True)
    parser.add_argument("--test-path", action="append", required=True)
    parser.add_argument("--resume", action="store_true")
    values = parser.parse_args()
    return ProofInput(values.run_id, values.project_id, values.requirement_file,
        values.state_root.resolve(), values.evidence_root.resolve(), values.reasoning_model,
        tuple(values.production_path), tuple(values.test_path),
        StrictTddRunMode.RESUME if values.resume else StrictTddRunMode.START)


def main() -> int:
    arguments = parse()
    try:
        report = asyncio.run(execute(arguments))
    except (ValueError, OSError, RuntimeError, PythonProbePreflightError,
            SubprocessError, StrictTddReceiptDeliveryError) as error:
        report = ProofReport(ProofStatus.BLOCKED, f"{type(error).__name__}: {error}")
        PostBehaviorEvidenceStore(arguments.proof_root).record("proof_blocker", report)
    print(json.dumps(asdict(report), sort_keys=True, indent=2))
    return 0 if report.status == ProofStatus.PASSED else 2


if __name__ == "__main__":
    raise SystemExit(main())
