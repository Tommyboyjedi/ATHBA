"""One composition-facing facade for the PR23 microcycle revision lifecycle."""

from __future__ import annotations

from dataclasses import dataclass

from core.development.microcycle_revision_git import MicrocycleGitClient
from core.development.microcycle_revision_lifecycle import (
    CanonicalDevelopmentBasePromoter,
    RackAiRevisionBindingFactory,
    RevisionCompletionService,
    RevisionRecoveryService,
    RevisionStateInitialiser,
    WorkingRevisionAdvancer,
)
from core.development.microcycle_revision_state import (
    MicrocycleRevisionState,
    RevisionBindingRequest,
    RevisionCompletionRequest,
    RevisionInitialisationRequest,
    RevisionRecoveryRequest,
    RevisionTransitionRequest,
    RevisionTransitionResult,
)
from core.development.microcycle_revision_store import MicrocycleRevisionRepository
from core.execution.rack_ai_request import RepositoryBinding


@dataclass(frozen=True)
class RevisionLifecycleDependencies:
    repository: MicrocycleRevisionRepository
    git: MicrocycleGitClient


class MicrocycleRevisionLifecycle:
    """Composition seam for typed working-ref and canonical-base transitions."""

    def __init__(self, dependencies: RevisionLifecycleDependencies):
        self.initialiser = RevisionStateInitialiser(dependencies.repository, dependencies.git)
        self.advancer = WorkingRevisionAdvancer(dependencies.repository, dependencies.git)
        self.promoter = CanonicalDevelopmentBasePromoter(dependencies.repository, dependencies.git)
        self.recovery = RevisionRecoveryService(dependencies.repository, dependencies.git)
        self.completion = RevisionCompletionService(dependencies.repository, dependencies.git)
        self.bindings = RackAiRevisionBindingFactory(self.recovery, dependencies.git)

    def initialise(self, request: RevisionInitialisationRequest) -> MicrocycleRevisionState:
        return self.initialiser.initialise(request)

    def advance(self, request: RevisionTransitionRequest) -> RevisionTransitionResult:
        return self.advancer.advance(request)

    def promote(self, request: RevisionTransitionRequest) -> RevisionTransitionResult:
        return self.promoter.promote(request)

    def recover(self, request: RevisionRecoveryRequest) -> MicrocycleRevisionState:
        return self.recovery.recover(request)

    def complete(self, request: RevisionCompletionRequest) -> MicrocycleRevisionState:
        return self.completion.complete(request)

    def binding(self, request: RevisionBindingRequest) -> RepositoryBinding:
        return self.bindings.build(request)