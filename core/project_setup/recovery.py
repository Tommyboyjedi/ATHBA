"""Explicit historical evidence for pre-journal failed setup; never arbitrary adoption."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
import json
from pathlib import Path

from core.development.project_environment_git import (
    SEED_COMMIT_MESSAGE, SEED_GITIGNORE, SEED_USER_EMAIL, SEED_USER_NAME,
)
from core.project_setup.architecture import ArchitectureApproval, RepositoryPolicy, content_hash
from core.project_setup.progress import SetupProgress, SetupProgressVerifier, SetupWork


@dataclass(frozen=True)
class SetupEvidenceFile:
    path: Path
    sha256: str


@dataclass(frozen=True)
class HistoricalSetupEvidence:
    failed_setup: SetupEvidenceFile
    failed_run: SetupEvidenceFile
    repository_snapshot: SetupEvidenceFile


@dataclass(frozen=True)
class HistoricalSetupContext:
    work: SetupWork
    approval: ArchitectureApproval


def _read(reference: SetupEvidenceFile) -> dict:
    path = reference.path
    if not path.is_absolute() or path.resolve() != path or not path.is_file():
        raise ValueError("historical setup evidence requires an exact ordinary absolute file")
    data = path.read_bytes()
    if sha256(data).hexdigest() != reference.sha256:
        raise ValueError("historical setup evidence hash changed")
    return json.loads(data)


class HistoricalSetupRecovery:
    """Correlate retained failed-run authority, exact seed and historical file inventory."""

    def __init__(self, verifier: SetupProgressVerifier):
        self.verifier = verifier

    def verify(self, context: HistoricalSetupContext, evidence: HistoricalSetupEvidence) -> SetupProgress:
        failed = _read(evidence.failed_setup)
        run = _read(evidence.failed_run)
        snapshot = _read(evidence.repository_snapshot)
        work = context.work
        self._failed((context, failed))
        approved = run.get("approved_handoff", {})
        decision = approved.get("decision", {})
        if (approved.get("approval") != asdict(context.approval)
                or content_hash(decision) != work.architecture_sha256
                or decision.get("repository_policy") != RepositoryPolicy.CREATE_OR_REUSE.value
                or decision.get("existing_repository") is not None):
            raise ValueError("historical run does not retain this exact approved new-project architecture")
        expected = Path(run.get("state_root", "")) / "projects" / work.project_id / "repository"
        if (str(expected) != work.repository_root or run.get("project_id") != work.project_id
                or run.get("status") != "failed" or run.get("prepare_requested") is not True
                or run.get("bde_execution_attempted") is not False or run.get("model_interactions") != 0):
            raise ValueError("historical run is not this failed preparation before delivery")
        if (snapshot.get("repository") != work.repository_root
                or snapshot.get("files_sha256") != work.expected_files
                or snapshot.get("trusted_scaffold_revision") is not None
                or snapshot.get("delivery_branches") or snapshot.get("integration_receipts")):
            raise ValueError("historical repository snapshot does not identify the approved unfinished scaffold")
        seed = snapshot.get("head")
        if not isinstance(seed, str) or len(seed) != 40:
            raise ValueError("historical repository snapshot has no exact seed revision")
        provenance = tuple((str(ref.path), ref.sha256) for ref in (
            evidence.failed_setup, evidence.failed_run, evidence.repository_snapshot))
        record = self.verifier.snapshot(SetupProgress(
            work, seed_revision=seed, files_written=True, provenance=provenance))
        self._seed(record)
        root = Path(work.repository_root)
        if self.verifier.run(root, "status", "--short") != snapshot.get("status"):
            raise ValueError("historical scaffold status changed since its retained observation")
        if self.verifier.run(root, "write-tree").strip() != self.verifier.run(
                root, "rev-parse", seed + "^{tree}").strip():
            raise ValueError("historical scaffold index differs from its retained initialization")
        return record

    def _failed(self, request: tuple[HistoricalSetupContext, dict]) -> None:
        context, failed = request
        work, approval = context.work, context.approval
        identities = ("project_id", "setup_identity", "architecture_sha256", "specification_sha256")
        if any(failed.get(name) != getattr(work, name) for name in identities):
            raise ValueError("historical failed setup authority differs from the approved setup")
        if (failed.get("approval_identity") != approval.identity or failed.get("approval_kind") != approval.kind.value
                or failed.get("status") != "failed" or failed.get("environment_verified") is not False
                or failed.get("scaffold_revision") is not None or failed.get("last_accepted_revision") is not None
                or failed.get("deliveries") or failed.get("active_delivery")):
            raise ValueError("historical evidence does not identify a failed, unaccepted, undelivered setup")
        commands = failed.get("commands", [])
        if not commands or commands[-1].get("returncode") in (None, 0):
            raise ValueError("historical recovery requires retained failed readiness-command evidence")

    def _seed(self, record: SetupProgress) -> None:
        root, seed = Path(record.work.repository_root), record.seed_revision
        if seed is None:
            raise ValueError("historical recovery requires an exact initialization revision")
        run = self.verifier.run
        if record.references != {record.canonical_ref: seed}:
            raise ValueError("historical setup no longer has only its original main ref")
        if run(root, "rev-list", "--parents", "-n", "1", seed).split() != [seed]:
            raise ValueError("historical setup seed is not an initial commit")
        if run(root, "ls-tree", "--name-only", seed).strip() != ".gitignore":
            raise ValueError("historical setup seed contains unowned implementation")
        if run(root, "show", seed + ":.gitignore") != SEED_GITIGNORE:
            raise ValueError("historical setup seed differs from ATHBA initialization")
        author = run(root, "show", "-s", "--format=%an%n%ae%n%s", seed).splitlines()
        if author != [SEED_USER_NAME, SEED_USER_EMAIL, SEED_COMMIT_MESSAGE]:
            raise ValueError("historical setup seed lacks the retained ATHBA initialization identity")
