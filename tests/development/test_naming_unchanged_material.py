"""Naming inspects accepted declarations even when behavioral work only edits tests."""
from dataclasses import replace
import pytest
from core.development.post_behavior_domain import (
    ChangeCandidate, PostBehaviorAssessment, PostBehaviorEntry, PostBehaviorPass,
    PostBehaviorPhase, PostBehaviorState, PostBehaviorStatus, ValidationEvidence)
from core.development.post_behavior_assessment import (
    IdentifierRename, NamingAssessmentInput, NamingAssessor, NamingDecision, NamingMaterial)
from core.development.post_behavior_validation import (
    PostBehaviorCandidateAuthority, PostBehaviorPassAuthority, PostBehaviorSource)
from core.development.required_public_signature import RequiredPublicSignature
from core.development.specification_evidence_policy import RevisionFile, SpecificationSnapshot

SOURCE = "class Calculator:\n    def double(self, x):\n        return x * 2\n    def triple(self, x):\n        return x * 3\n"
ENTRY, ACCEPTED, CANDIDATE = "1"*40, "2"*40, "3"*40
TEST = "from arithmetic import Calculator\ndef test_double():\n    assert Calculator().double(3) == 6\n"

class Git:
    def __init__(self, current=SOURCE):
        self.current = current
    def snapshot(self, revision):
        production = SOURCE if revision == ENTRY else self.current
        if revision == CANDIDATE:
            production = production.replace("double(self, x)", "double(self, amount)").replace("x * 2", "amount * 2")
        return SpecificationSnapshot(revision, (
            RevisionFile("arithmetic.py", production), RevisionFile("tests/test_arithmetic.py", TEST),
            RevisionFile("other.py", "UNOWNED = True\n")))
    def validate_candidate(self, pair):
        assert pair == (ACCEPTED, CANDIDATE)

def naming_state():
    entry = PostBehaviorEntry("delivery", ENTRY, ACCEPTED, ("arithmetic.py",), "authority",
        ValidationEvidence(ACCEPTED, True, ("gatekeeper",)))
    return PostBehaviorState(entry, ACCEPTED, PostBehaviorStatus.NAMING_ASSESSMENT_PENDING,
        PostBehaviorPass(PostBehaviorPhase.NAMING, 1, ACCEPTED))

@pytest.mark.parametrize("current", [SOURCE, SOURCE.replace("x * 3", "x * 3 + 0")])
@pytest.mark.asyncio
async def test_naming_includes_unchanged_owned_declaration(current):
    source = PostBehaviorSource(Git(current))
    production = source.focused(naming_state())
    assert tuple(file.path for file in production.files) == ("arithmetic.py",)
    assert "def double(self, x)" in production.files[0].source
    material = NamingMaterial("double(amount)", ("Calculator", "double", "amount"),
        (RequiredPublicSignature("Calculator", "double", ("amount",), "double(amount)"),))
    decision = await NamingAssessor(NoModel()).reason(NamingAssessmentInput(material, production))
    assert decision == NamingDecision(IdentifierRename("x", "amount", "Calculator", "double", 0))

class NoModel:
    async def reason(self, request):
        raise AssertionError("Explicit scoped declaration mismatch is mechanical")

@pytest.mark.parametrize("current", [SOURCE, SOURCE.replace("x * 3", "x * 3 + 0")])
def test_refactor_keeps_changed_only_projection(current):
    from core.development.post_behavior_validation import PostBehaviorProductionRevision
    state = naming_state()
    result = PostBehaviorSource(Git(current)).for_revision(
        PostBehaviorProductionRevision(state.entry, ACCEPTED, PostBehaviorPhase.REFACTORING))
    assert all("def double" not in file.source for file in result.files)
    assert bool(result.files) == (current != SOURCE)

def test_candidate_authority_reconstructs_naming_phase_slice():
    state = naming_state()
    source = PostBehaviorSource(Git())
    decision = NamingDecision(IdentifierRename("x", "amount", "Calculator", "double", 0))
    change = replace(state.active_pass,
        assessment=PostBehaviorAssessment(decision, source.focused(state).identity),
        submission_id="rename", candidate=ChangeCandidate(CANDIDATE, ("execution",)))
    PostBehaviorCandidateAuthority(source).verify_pass(PostBehaviorPassAuthority(state.entry, change))

def test_naming_scope_still_rejects_missing_owned_file():
    state = naming_state()
    state = replace(state, entry=replace(state.entry, production_paths=("missing.py",)))
    with pytest.raises(ValueError, match="disappeared"):
        PostBehaviorSource(Git()).focused(state)
