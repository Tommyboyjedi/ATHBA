# PR17 Provisional Semantic Progression

## Purpose

This document defines the generic progression architecture required when a GREEN candidate is mechanically correct and reusable, but semantic completion still depends on later requirements.

The design separates development progress from semantic approval so ATHBA can keep moving through an actionable dependency graph without discarding accepted GREEN work.

## Explicit State

The run state now persists four separate concepts:

- `development_base_revision`: the latest accepted executable revision that future RED and GREEN work must resume from.
- `semantic_base_revision`: the latest revision whose requirement coverage is semantically approved.
- `provisional_requirement_state`: a requirement with accepted GREEN evidence that is still waiting on later semantic obligations.
- `open_semantic_obligation`: a persisted record that names the owning requirement, the blocking requirement refs, and the rationale for later closure.

`SemanticProgressLedger` stores provisional requirements, open obligations, and obligation resolution history.

## Progression Rules

1. GREEN acceptance advances `development_base_revision` immediately.
2. Semantic approval advances `semantic_base_revision` and semantically completes the reviewed requirement.
3. A provisional semantic verdict keeps the accepted GREEN revision, records the provisional requirement, records one or more open obligations, and returns the run to `tdd_ready`.
4. Resume always starts from `development_base_revision`, not `semantic_base_revision`.
5. Completion is illegal while any provisional requirement or open semantic obligation remains unresolved.

## Actionable Selection

Requirement selection is no longer strict depth-first over semantically approved prerequisites.

A requirement is actionable when:

- it is not already semantically approved;
- it is not itself the owner of an open obligation;
- it is not already stored as provisional; and
- all of its dependencies are mechanically available through either semantic approval or provisional GREEN.

This allows the scheduler to move to unrelated or downstream actionable work instead of rerunning a blocked prerequisite cycle.

A targeted requirement remains a priority signal only. If it is actionable, it is ordered first. It does not make other actionable requirements illegal.

## Obligation Closure

Obligation closure is recalculated whenever the lane re-enters `tdd_ready` or `approved`, and again after semantic approvals.

An open obligation resolves when all of its `blocking_requirement_refs` are semantically approved. When the last open obligation for a provisional requirement resolves, ATHBA promotes that requirement into `completed_requirement_refs` without recreating the original GREEN candidate.

Resolution history preserves the semantic revision that closed the obligation.

## Persistence and Authority

The persisted snapshot now stores both development and semantic base revisions. `current_trusted_revision` remains as the compatibility alias for the development base.

Repository material for future planning and execution is read from the development base. Specification gatekeeping still derives final semantic proof only from semantically approved review history and accepted tests tied to semantic revisions.

## Regression Coverage

The regression suite covers two unrelated generic domains and the proof-blocker shape that motivated this work:

- sequential semantic progression with aligned development and semantic bases;
- provisional GREEN recording;
- continuation from a provisional revision;
- non-depth-first actionable selection;
- later obligation closure without rerunning GREEN;
- dependency-cycle rejection at contract validation;
- prevention of repeated blocked selection for an open-obligation owner;
- regression reproduction for a previously unavailable prerequisite followed by provisional progress and correct resume;
- repository-material resume from development base ahead of semantic base; and
- final completion blocked while unresolved obligations remain.
