"""Immutable generic contribution authority; language mechanics stay in adapters."""
from __future__ import annotations

from typing import TYPE_CHECKING

from core.development.production_reduction_domain import ConsolidatedReductionRequest, ReductionRequest
from core.development.production_reduction_syntax import ReductionContributionSource, ReductionSource
from core.development.required_public_signature import RequiredPublicSignature

if TYPE_CHECKING:
    from core.development.production_reduction_git import BoundedReductionGit


def validate_contributions(git: BoundedReductionGit, request: ConsolidatedReductionRequest) -> None:
    windows = request.scope.windows
    if not windows or not any(item.selected for item in windows):
        raise ValueError("completion reduction requires selected immutable contributions")
    cursor = request.baseline_revision
    for window in windows:
        if window.before_revision != cursor:
            raise ValueError("completion contribution history is incomplete or interleaved")
        for revision in (window.before_revision, window.after_revision):
            if git.run(("rev-parse", "--verify", f"{revision}^{{commit}}")).decode().strip() != revision:
                raise ValueError("contribution requires exact immutable commit identities")
        git.run(("merge-base", "--is-ancestor", window.before_revision, window.after_revision))
        cursor = window.after_revision
    git.run(("merge-base", "--is-ancestor", cursor, request.tests_revision))
    # Approval may change tests, but cannot introduce unowned production.
    for path in request.production_paths:
        if git.source((cursor, path)) != git.source((request.tests_revision, path)):
            raise ValueError("completion production changed after contribution history")


def scoped_source(git: BoundedReductionGit, value: tuple[ReductionRequest, str, str]) -> ReductionSource:
    request, path, revision = value
    contributions: tuple[ReductionContributionSource, ...] = ()
    identifiers: tuple[RequiredPublicSignature, ...] = ()
    if isinstance(request, ConsolidatedReductionRequest):
        contributions = tuple(ReductionContributionSource(
            git.source((window.before_revision, path)),
            git.source((window.after_revision, path)), window.selected,
        ) for window in request.scope.windows)
        identifiers = request.scope.protected_identifiers
    return ReductionSource(path, git.source((request.baseline_revision, path)),
                           git.source((revision, path)), contributions, identifiers)
