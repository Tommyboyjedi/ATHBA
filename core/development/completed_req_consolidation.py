"""One optional consolidation opportunity after durable REQ acceptance."""
from __future__ import annotations

from dataclasses import asdict, dataclass, replace
import json
from pathlib import Path

from core.atomic_json_file import read_json_file
from core.development.consolidation_evidence import CaseSnapshot, SupersessionRecord
from core.development.consolidation_git import (
    ConsolidationGit, ConsolidationPromotion, TestReplacementInput,
)
from core.development.consolidation_journal import ConsolidationJournal, ConsolidationOutcome, ConsolidationProgress
from core.development.consolidation_language import ConsolidationLanguage, ConsolidationTestSource
from core.development.consolidation_material import (
    ConsolidationContext, ConsolidationMaterial, SelectedConsolidation, checkpoint_identity,
)
from core.development.consolidation_reasoning import (
    ConsolidationContextLimit, ConsolidationCoverageMissing, ConsolidationReasoning, ConsolidationReplacement,
)
from core.development.consolidation_submission import ConsolidationProtocolFailure, ConsolidationSubmission
from core.development.consolidation_validation import ConsolidationValidation, ConsolidationValidationInput
from core.development.project_environment_port import PreparedProjectEnvironment
from core.development.strict_tdd_feature_domain import StrictTddFeatureState
from core.development.test_material import TestMaterialAdapter, TestSourceRequest


@dataclass(frozen=True)
class ConsolidationDependencies:
    state_root: Path
    material: ConsolidationMaterial
    reasoning: ConsolidationReasoning
    language: ConsolidationLanguage
    tests: TestMaterialAdapter
    git: ConsolidationGit
    validation: ConsolidationValidation
    environment: PreparedProjectEnvironment


class CompletedReqConsolidation:
    """Coordinate one bounded optional checkpoint without changing TDD history."""

    def __init__(self, dependencies: ConsolidationDependencies):
        self.dependencies = dependencies

    async def advance(self, context: ConsolidationContext) -> StrictTddFeatureState | None:
        state = context.state
        if not state.completed_behaviors or state.current_scenario_id is not None:
            return None
        identity = checkpoint_identity(state)
        if identity in state.consolidation_checks:
            return None
        journal = ConsolidationJournal(self.dependencies.state_root, identity)
        with journal.locked():
            progress = journal.load()
            if progress is None:
                progress = ConsolidationProgress(str(state.canonical_development_base))
                journal.save(progress)
            if state.canonical_development_base not in {progress.baseline_revision, progress.final_revision}:
                raise ValueError("consolidation accepted baseline changed during checkpoint")
            if progress.outcome is None:
                self.dependencies.git.assert_clean(progress.baseline_revision)
                selected = self.dependencies.material.prepare((context, identity))
                if selected is None:
                    progress = replace(progress, outcome=ConsolidationOutcome.NO_CONSOLIDATION,
                        diagnostic="No bounded related active group or supported context")
                    journal.save(progress)
                else:
                    authority = json.loads(json.dumps(asdict(selected), sort_keys=True))
                    _freeze(journal, ("selected-authority.json", authority))
                    journal.save(replace(progress, member_refs=selected.member_refs))
                    pipeline = ConsolidationCandidate(self.dependencies)
                    try:
                        progress = await pipeline.run((selected, journal))
                    except (ConsolidationProtocolFailure, ConsolidationContextLimit) as error:
                        progress = replace(journal.load() or progress,
                            outcome=ConsolidationOutcome.REJECTED, diagnostic="Optional proposal unavailable: " + str(error))
                        journal.save(progress)
            if progress.supersession is not None:
                record = SupersessionRecord.from_dict(progress.supersession)
                self.dependencies.git.publish(ConsolidationPromotion(
                    state.project_id, progress.baseline_revision, record.final_revision),
                    self.dependencies.environment)
                return replace(state, canonical_development_base=record.final_revision,
                    evidence_consolidations=(*state.evidence_consolidations, record),
                    consolidation_checks=(*state.consolidation_checks, identity),
                    evidence_refs=(*state.evidence_refs, str(journal.root / "checkpoint.json")))
            return replace(state, consolidation_checks=(*state.consolidation_checks, identity),
                evidence_refs=(*state.evidence_refs, str(journal.root / "checkpoint.json")))


class ConsolidationCandidate:
    """Freeze semantically approved tests before deterministic production reduction."""

    def __init__(self, dependencies: ConsolidationDependencies):
        self.dependencies = dependencies

    async def run(self, value: tuple[SelectedConsolidation, ConsolidationJournal]) -> ConsolidationProgress:
        selected, journal = value
        deps = self.dependencies
        context = selected.reasoning
        submission = ConsolidationSubmission(deps.reasoning, journal)
        proposal = await submission.decode(("proposal", deps.reasoning.proposal_request(context)),
            lambda text: deps.reasoning.decode_proposal(context, text))
        if proposal is None:
            return _decline(journal, "Proposal declined consolidation", no_change=True)
        replacement = await submission.decode(("replacement", deps.reasoning.author_request(context, proposal)),
            lambda text: self._replacement((selected, journal), text))
        progress = journal.load()
        if progress is None:
            raise ValueError("consolidation checkpoint disappeared")
        try:
            source, _authority = deps.language.validate(ConsolidationTestSource(
                context.checkpoint_id, context.replacement_test_name, replacement.source,
                selected.production_paths[0], progress.baseline_revision))
        except ValueError as error:
            return _decline(journal, "Replacement syntax/static validation: " + str(error))
        replacement = replace(replacement, source=source)
        review = await submission.decode(("review", deps.reasoning.review_request(context, replacement)),
            lambda text: deps.reasoning.decode_review(context, text))
        if review.status != "approved":
            return _decline(journal, "Semantic preservation rejected: " + review.rationale)
        _freeze(journal, ("semantic-approval.json", {
            "decision": review.to_dict(), "replacement_source": source,
            "coverage": [item.to_dict() for item in replacement.coverage],
            "interpretation": "Independent preservation judgment, not mapping-as-equivalence proof",
        }))
        if progress.test_revision is None:
            try:
                revision = deps.git.create(TestReplacementInput(progress.baseline_revision,
                    selected.previous_tests, source, context.replacement_test_name))
            except ValueError as error:
                return _decline(journal, "Test-only candidate rejected: " + str(error))
            progress = replace(progress, test_revision=revision)
            journal.save(progress)
        request = deps.validation.request(ConsolidationValidationInput(
            selected, str(progress.test_revision), source))
        regression = deps.validation.accept(request, journal)
        if regression is None:
            return _decline(journal, "Replacement failed unchanged accepted production")
        reduced = deps.validation.reduce(request, regression)
        record = _record((selected, replacement), (progress, reduced.revision, reduced.evidence_ref, journal, deps.tests, proposal.description))
        progress = replace(progress, outcome=ConsolidationOutcome.VERIFIED, final_revision=reduced.revision,
            supersession=record.to_dict(), reduction_evidence=reduced.evidence_ref)
        journal.save(progress)
        return progress

    def _replacement(self, value: tuple[SelectedConsolidation, ConsolidationJournal],
                     text: str) -> ConsolidationReplacement:
        selected, journal = value
        context = selected.reasoning
        try:
            return self.dependencies.reasoning.decode_replacement(context, text)
        except ConsolidationCoverageMissing as omission:
            progress = journal.load()
            if progress is None:
                raise ValueError("consolidation checkpoint disappeared")
            try:
                self.dependencies.language.validate(ConsolidationTestSource(
                    context.checkpoint_id, context.replacement_test_name, omission.replacement.source,
                    selected.production_paths[0], progress.baseline_revision))
            except (ValueError, SyntaxError) as error:
                raise ConsolidationProtocolFailure(
                    str(omission) + "; replacement syntax/static validation: " + str(error)
                ) from error
            raise


def _freeze(journal: ConsolidationJournal, item: tuple[str, object]) -> None:
    name, value = item
    path = journal.root / name
    if path.exists() and read_json_file(path) != value:
        raise ValueError("consolidation selected authority changed on resume")
    journal.record(item)


def _decline(journal: ConsolidationJournal, diagnostic: str,
             no_change: bool = False) -> ConsolidationProgress:
    progress = journal.load()
    if progress is None:
        raise ValueError("consolidation checkpoint disappeared")
    result = replace(progress, outcome=(ConsolidationOutcome.NO_CONSOLIDATION if no_change else ConsolidationOutcome.REJECTED), diagnostic=diagnostic)
    journal.save(result)
    return result


def _record(selection: tuple[SelectedConsolidation, ConsolidationReplacement],
            authority: tuple[ConsolidationProgress, str, str, ConsolidationJournal, TestMaterialAdapter, str]) -> SupersessionRecord:
    selected, replacement = selection
    progress, final, reduction_evidence, journal, tests, description = authority
    name = selected.reasoning.replacement_test_name
    source = tests.extract(TestSourceRequest(replacement.source, name))
    if source is None:
        raise ValueError("approved replacement test identity is unavailable")
    source_refs = tuple(dict.fromkeys(ref for case in selected.previous_tests for ref in case.source_refs))
    case = CaseSnapshot(name, tests.test_path(name), source, str(progress.test_revision),
                        selected.member_refs, source_refs)
    return SupersessionRecord(selected.reasoning.checkpoint_id, selected.member_refs,
        selected.previous_tests, (case,), description, replacement.coverage,
        progress.baseline_revision, str(progress.test_revision), final,
        (str(journal.root / "semantic-approval.json"), str(journal.root / "test-acceptance.json"), reduction_evidence))
