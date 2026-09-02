import json
from pathlib import Path

import pytest

from core.datastore.repos.scenario_draft_state_repo import ScenarioDraftStateRepo
from core.development.microcycle_domain import FinalTestMaterialisationRequest, LanguageAdapterCatalog
from core.development.python_pytest_adapter import PythonPytestAdapter
from core.development.scenario_drafting import (
    ScenarioDraftingDependencies,
    ScenarioDraftingService,
    ScenarioIntentReviewer,
)
from core.development.scenario_drafting_domain import (
    MAX_TESTER_SCENARIO_ATTEMPTS,
    ScenarioDraftRequest,
    ScenarioDraftStatus,
    ScenarioRepositoryFacts,
)
from core.development.tdd_progression import TddStepProposal
from core.execution.rack_ai_contract import RepositoryBinding
from core.execution.reasoning_gateway import ReasoningResult
from core.execution.work_unit_gateway import WorkUnitExecutionResult


class FakeGateway:
    def __init__(self, results):
        self.results = list(results)
        self.calls = []

    async def execute(self, unit, binding):
        self.calls.append((unit, binding))
        return self.results.pop(0)


class FakeReasoningGateway:
    def __init__(self, responses):
        self.responses = list(responses)
        self.requests = []

    async def reason(self, request):
        self.requests.append(request)
        return ReasoningResult(self.responses.pop(0), "fake", "fake")


class MemoryStateStore:
    def __init__(self):
        self.states = {}

    def load(self, scenario_id):
        return self.states.get(scenario_id)

    def save(self, state):
        self.states[state.scenario_id] = state


class CandidateSourceReader:
    def __init__(self, sources):
        self.sources = dict(sources)
        self.calls = []

    def read(self, revision, test_path):
        self.calls.append((revision, test_path))
        return self.sources[revision]

    def resolve(self, ref):
        return ref


def ticket(kind):
    if kind == "catalog":
        return TddStepProposal(
            "catalog-ticket",
            ["SRC-CATALOG"],
            "Adding an item makes it visible by its identifier.",
            "tests/test_catalog.py::test_catalog_records_item",
            "item_id('a') returns 'a' after adding the item.",
            "tests/test_catalog.py",
            "catalog.py",
            "obsolete immediate red objective",
            "obsolete developer objective",
            "Catalog insertion is independently observable.",
        )
    return TddStepProposal(
        "profile-ticket",
        ["SRC-PROFILE"],
        "A profile exposes its display name.",
        "tests/test_profile.py::test_profile_exposes_display_name",
        "display_name returns the supplied name.",
        "tests/test_profile.py",
        "profile.py",
        "obsolete immediate red objective",
        "obsolete developer objective",
        "The profile behavior is unrelated to catalog storage.",
    )


def candidate(kind, *, rationale="The complete example demonstrates the requested observable behavior."):
    value = ticket(kind)
    if kind == "catalog":
        body = "    catalog = Catalog()\n    catalog.add('a')\n    assert catalog.item_id('a') == 'a'\n"
        imported = "from catalog import Catalog"
    else:
        body = "    profile = Profile('Ada')\n    assert profile.display_name() == 'Ada'\n"
        imported = "from profile import Profile"
    return (
        f"# ATHBA-SCENARIO-RATIONALE: {rationale}\n"
        f"# ATHBA-SOURCE-REFS: {', '.join(value.requirement_refs)}\n"
        "import pytest\n"
        f"{imported}\n\n"
        f"def {value.test_name.rsplit('::', 1)[1]}():\n{body}"
    )


def request(kind, base="a" * 40):
    value = ticket(kind)
    return ScenarioDraftRequest(
        scenario_id=f"scenario-{kind}",
        ticket=value,
        source_requirement_refs=tuple(value.requirement_refs),
        language_id="python",
        test_framework="pytest",
        allowed_test_path=value.test_path,
        repository_facts=ScenarioRepositoryFacts(base, (value.production_path, value.test_path), "bounded production", "bounded tests"),
        development_base_revision=base,
    )


def binding(base="a" * 40):
    return RepositoryBinding("scenario-fixture", "main", base)


def accepted(work_unit_id, revision, change_id):
    return WorkUnitExecutionResult(
        work_unit_id=work_unit_id,
        accepted=True,
        status="checks_passed",
        change_id=change_id,
        accepted_revision=revision,
        evidence_location=f"evidence/{change_id}.json",
        branch=revision,
    )


def components(results, responses, sources, store=None):
    gateway = FakeGateway(results)
    reasoning = FakeReasoningGateway(responses)
    reader = CandidateSourceReader(sources)
    dependencies = ScenarioDraftingDependencies(
        gateway,
        ScenarioIntentReviewer(reasoning),
        LanguageAdapterCatalog((PythonPytestAdapter(),)),
        reader,
        store or MemoryStateStore(),
    )
    return ScenarioDraftingService(dependencies), gateway, reasoning, reader


def approval(ref):
    return json.dumps({
        "disposition": "approved",
        "feedback": "The scenario covers the requested observable behavior.",
        "evidence_refs": [ref],
    })


@pytest.mark.asyncio
async def test_approved_catalog_scenario_is_frozen_from_isolated_candidate_without_base_promotion():
    value, gateway, reasoning, reader = components(
        [accepted("catalog-ticket--scenario-draft-1", "b" * 40, "draft-1")],
        [approval("SRC-CATALOG")],
        {"b" * 40: candidate("catalog")},
    )

    outcome = await value.draft(request("catalog"), binding())

    assert outcome.approved
    state = outcome.state
    frozen = state.approved_microcycle
    assert frozen is not None
    assert frozen.development_base_revision == "a" * 40
    assert frozen.scenario_draft.source == candidate("catalog")
    assert frozen.scenario_draft.canonical_test_identity == ticket("catalog").test_name
    assert frozen.scenario_draft.source_requirement_refs == ("SRC-CATALOG",)
    assert frozen.intent.status == "approved"
    assert frozen.model.adapter_version == "1.0.0"
    assert frozen.frontier.index == 0
    assert [item.kind for item in frozen.fragments] == ["production_import", "constructor", "call", "assertion"]
    assert state.attempts[0].candidate_revision == "b" * 40
    assert gateway.calls[0][1].base_sha == "a" * 40
    unit = gateway.calls[0][0]
    assert "frontier" in unit.objective
    assert len(reader.calls) == 1
    prompt = reasoning.requests[0].prompt
    assert "production_path" not in prompt
    assert "obsolete developer objective" not in prompt
    assert "replacement test code" in prompt
    assert len(gateway.calls) == 1


@pytest.mark.asyncio
async def test_wrong_profile_behavior_is_rejected_with_descriptive_feedback_and_no_freeze():
    value, gateway, _reasoning, _reader = components(
        [accepted("profile-ticket--scenario-draft-1", "c" * 40, "draft-1")],
        [json.dumps({
            "disposition": "wrong_behavior",
            "feedback": "This checks profile construction but does not demonstrate display-name exposure.",
            "evidence_refs": ["SRC-PROFILE"],
        })],
        {"c" * 40: candidate("profile")},
    )

    outcome = await value.draft(request("profile"), binding())

    assert not outcome.approved
    assert outcome.state.attempts[0].intent.status == "wrong_behavior"
    assert "does not demonstrate" in outcome.state.attempts[0].feedback
    assert outcome.state.approved_microcycle is None
    assert len(gateway.calls) == 1


@pytest.mark.asyncio
async def test_descriptive_repair_uses_a_new_attempt_scoped_change_id():
    value, gateway, _reasoning, _reader = components(
        [
            accepted("catalog-ticket--scenario-draft-1", "d" * 40, "draft-1"),
            accepted("catalog-ticket--scenario-draft-2", "e" * 40, "draft-2"),
        ],
        [
            json.dumps({
                "disposition": "repair_required",
                "feedback": "Show the observable lookup after the add operation.",
                "evidence_refs": ["SRC-CATALOG"],
            }),
            approval("SRC-CATALOG"),
        ],
        {"d" * 40: candidate("catalog"), "e" * 40: candidate("catalog", rationale="The repair now proves the lookup.")},
    )

    first = await value.draft(request("catalog"), binding())
    second = await value.draft(request("catalog"), binding())

    assert not first.approved and second.approved
    assert [call[0].change_key for call in gateway.calls] == [
        "catalog-ticket--scenario-draft-1--attempt-1",
        "catalog-ticket--scenario-draft-2--attempt-2",
    ]
    assert "Show the observable lookup" in gateway.calls[1][0].objective


@pytest.mark.asyncio
async def test_tester_scenario_attempts_stop_at_four():
    results = [
        accepted(f"catalog-ticket--scenario-draft-{number}", chr(100 + number) * 40, f"draft-{number}")
        for number in range(1, MAX_TESTER_SCENARIO_ATTEMPTS + 1)
    ]
    sources = {result.accepted_revision: candidate("catalog", rationale=f"Attempt {index} is independently stated.") for index, result in enumerate(results, 1)}
    responses = [
        json.dumps({
            "disposition": "insufficient_evidence",
            "feedback": "State the observable lookup explicitly.",
            "evidence_refs": ["SRC-CATALOG"],
        })
        for _ in results
    ]
    value, gateway, _reasoning, _reader = components(results, responses, sources)

    outcome = None
    for _ in range(MAX_TESTER_SCENARIO_ATTEMPTS):
        outcome = await value.draft(request("catalog"), binding())
    final = await value.draft(request("catalog"), binding())

    assert outcome is not None and outcome.state.status == ScenarioDraftStatus.DRAFTING.value
    assert final.state.status == ScenarioDraftStatus.ATTEMPTS_EXHAUSTED.value
    assert len(final.state.attempts) == MAX_TESTER_SCENARIO_ATTEMPTS
    assert len(gateway.calls) == MAX_TESTER_SCENARIO_ATTEMPTS


@pytest.mark.asyncio
async def test_malformed_intent_response_gets_one_constrained_json_repair():
    value, gateway, reasoning, _reader = components(
        [accepted("catalog-ticket--scenario-draft-1", "f" * 40, "draft-1")],
        ["not json", approval("SRC-CATALOG")],
        {"f" * 40: candidate("catalog")},
    )

    outcome = await value.draft(request("catalog"), binding())

    assert outcome.approved
    assert len(gateway.calls) == 1
    assert [item.purpose for item in reasoning.requests] == [
        "athba_scenario_intent_review",
        "athba_scenario_intent_json_repair",
    ]


@pytest.mark.asyncio
async def test_resume_after_approval_reuses_durable_frozen_state_without_submission(tmp_path):
    store = ScenarioDraftStateRepo(tmp_path)
    first_service, first_gateway, _reasoning, _reader = components(
        [accepted("catalog-ticket--scenario-draft-1", "g" * 40, "draft-1")],
        [approval("SRC-CATALOG")],
        {"g" * 40: candidate("catalog")},
        store,
    )

    first = await first_service.draft(request("catalog"), binding())
    resumed_service, resumed_gateway, _resumed_reasoning, _resumed_reader = components(
        [],
        [],
        {},
        store,
    )
    second = await resumed_service.draft(request("catalog"), binding())

    assert first.approved and second.approved
    assert second.submitted_attempt is False
    assert second.state.approved_microcycle == first.state.approved_microcycle
    assert len(first_gateway.calls) == 1
    assert resumed_gateway.calls == []
    assert second.state.approved_microcycle.current_accepted_red_revision is None
    assert second.state.approved_microcycle.developer_attempts == ()
    assert second.state.attempts[0].candidate is not None
    assert second.state.attempts[0].candidate.actual_test_identity.endswith("test_catalog_records_item")


@pytest.mark.asyncio
async def test_stale_draft_state_is_not_reused_when_the_development_base_changes():
    store = MemoryStateStore()
    value, gateway, _reasoning, _reader = components([], [], {}, store)
    original = request("catalog", "a" * 40)
    store.save(
        value.state_store.load(original.scenario_id)
        or __import__("core.development.scenario_drafting", fromlist=["_initial_state"])._initial_state(original)
    )

    with pytest.raises(ValueError, match="stale scenario draft state"):
        await value.draft(request("catalog", "b" * 40), binding("b" * 40))

    assert gateway.calls == []


@pytest.mark.asyncio
async def test_candidate_submission_and_intent_review_have_isolated_effects():
    service, gateway, reasoning, _reader = components(
        [accepted("catalog-ticket--scenario-draft-1", "f" * 40, "draft-1")],
        [approval("SRC-CATALOG")],
        {"f" * 40: candidate("catalog")},
    )

    submitted = await service.submit_candidate(request("catalog"), binding())

    assert submitted.submitted_attempt
    assert len(gateway.calls) == 1
    assert reasoning.requests == []

    reviewed = await service.review_intent(request("catalog"))

    assert reviewed.approved
    assert len(gateway.calls) == 1
    assert len(reasoning.requests) == 1



def plain_catalog_candidate(name="test_model_catalog_behavior", *, prefix="", body=None):
    scenario_body = body or (
        "    catalog = Catalog()\n"
        "    catalog.add('a')\n"
        "    assert catalog.item_id('a') == 'a'\n"
    )
    return f"{prefix}from catalog import Catalog\n\ndef {name}():\n{scenario_body}"


@pytest.mark.asyncio
async def test_plain_candidate_uses_authoritative_provenance_and_adapter_canonicalisation():
    source = plain_catalog_candidate()
    service, _gateway, reasoning, _reader = components(
        [accepted("catalog-ticket--scenario-draft-1", "h" * 40, "draft-1")],
        [approval("SRC-CATALOG")],
        {"h" * 40: source},
    )

    outcome = await service.draft(request("catalog"), binding())

    frozen = outcome.state.approved_microcycle
    assert frozen is not None
    assert "# ATHBA-SCENARIO" not in frozen.scenario_draft.source
    assert frozen.scenario_draft.source_requirement_refs == request("catalog").source_requirement_refs
    assert frozen.scenario_draft.scenario_rationale == "The scenario covers the requested observable behavior."
    assert frozen.scenario_draft.canonical_test_identity == ticket("catalog").test_name
    assert "def test_catalog_records_item():" in frozen.scenario_draft.source
    attempt = outcome.state.attempts[0]
    assert attempt.candidate is not None
    assert attempt.candidate.actual_test_identity.endswith("test_model_catalog_behavior")
    assert attempt.static_analysis is not None
    assert attempt.static_analysis.production_reference_paths == ("catalog.py",)
    assert "test_catalog_records_item" in reasoning.requests[0].prompt
    final_artifact = PythonPytestAdapter().materialise_final_test(
        FinalTestMaterialisationRequest(
            frozen.model,
            frozen.fragments,
            frozen.development_base_revision,
        )
    )
    assert final_artifact.canonical_test_identity == ticket("catalog").test_name
    assert "def test_catalog_records_item():" in final_artifact.complete_source


@pytest.mark.asyncio
async def test_model_comments_are_ordinary_source_not_authoritative_metadata():
    source = plain_catalog_candidate(
        prefix="# ATHBA-SCENARIO-RATIONALE: untrusted rationale\n# ATHBA-SOURCE-REFS: WRONG-REF\n",
    )
    service, _gateway, _reasoning, _reader = components(
        [accepted("catalog-ticket--scenario-draft-1", "i" * 40, "draft-1")],
        [approval("SRC-CATALOG")],
        {"i" * 40: source},
    )

    outcome = await service.draft(request("catalog"), binding())

    frozen = outcome.state.approved_microcycle
    assert frozen is not None
    assert frozen.scenario_draft.source_requirement_refs == ("SRC-CATALOG",)
    assert frozen.scenario_draft.scenario_rationale == "The scenario covers the requested observable behavior."


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("source", "feedback"),
    [
        ("from catalog import Catalog\n", "exactly one supported"),
        (
            "from catalog import Catalog\n\ndef test_one():\n    assert Catalog\n\ndef test_two():\n    assert Catalog\n",
            "exactly one supported",
        ),
        ("from catalog import Catalog\n\ndef test_broken(:\n    pass\n", "invalid syntax"),
        (
            "class Catalog:\n    pass\n\ndef test_catalog():\n    assert Catalog\n",
            "substitute production implementation",
        ),
        (
            "from unittest.mock import patch\nfrom catalog import Catalog\n\ndef test_catalog():\n    with patch('catalog.Catalog'):\n        assert True\n",
            "mocks the behavior",
        ),
        (
            "from catalog import Catalog\n\ndef test_catalog():\n    try:\n        from catalog import Catalog\n    except ImportError:\n        assert True\n        return\n    assert Catalog\n",
            "missing-capability evasion",
        ),
        ("def test_catalog():\n    assert True\n", "does not reference"),
    ],
)
async def test_invalid_candidates_receive_specific_deterministic_feedback(source, feedback):
    service, gateway, reasoning, _reader = components(
        [accepted("catalog-ticket--scenario-draft-1", "j" * 40, "draft-1")],
        [],
        {"j" * 40: source},
    )

    outcome = await service.draft(request("catalog"), binding())

    assert outcome.state.attempts[0].status == "candidate_invalid"
    assert feedback in outcome.state.attempts[0].feedback
    assert reasoning.requests == []
    assert len(gateway.calls) == 1


@pytest.mark.asyncio
async def test_legitimate_test_data_helper_is_not_globally_prohibited():
    source = plain_catalog_candidate(
        prefix="ITEM_ID = 'a'\n\n",
        body=(
            "    catalog = Catalog()\n"
            "    catalog.add(ITEM_ID)\n"
            "    assert catalog.item_id(ITEM_ID) == ITEM_ID\n"
        ),
    )
    service, _gateway, reasoning, _reader = components(
        [accepted("catalog-ticket--scenario-draft-1", "k" * 40, "draft-1")],
        [approval("SRC-CATALOG")],
        {"k" * 40: source},
    )

    outcome = await service.draft(request("catalog"), binding())

    assert outcome.approved
    assert reasoning.requests


def test_language_neutral_domain_has_no_python_comment_or_name_policy():
    source = Path("core/development/microcycle_domain.py").read_text(encoding="utf-8")

    assert "ATHBA-SCENARIO-" not in source
    assert "ast." not in source



@pytest.mark.asyncio
async def test_repair_uses_verified_previous_candidate_ref_sha_source_and_structured_assessment():
    invalid = (
        '"""not allowed"""\n'
        'from catalog import Catalog\n\n'
        'def helper():\n'
        '    return Catalog\n\n'
        'def test_model_catalog_behavior():\n'
        '    assert Catalog\n'
    )
    repaired = plain_catalog_candidate()
    service, gateway, _reasoning, _reader = components(
        [
            accepted("catalog-ticket--scenario-draft-1", "m" * 40, "draft-1"),
            accepted("catalog-ticket--scenario-draft-2", "n" * 40, "draft-2"),
        ],
        [approval("SRC-CATALOG")],
        {"m" * 40: invalid, "n" * 40: repaired},
    )

    first = await service.draft(request("catalog"), binding())
    second = await service.submit_candidate(request("catalog"), binding())

    attempt = first.state.attempts[0]
    assert attempt.status == "candidate_invalid"
    assert attempt.candidate_assessment is not None
    assert {item.code for item in attempt.candidate_assessment.issues} >= {"module_docstring", "helper_function"}
    unit, repair_binding = gateway.calls[1]
    objective = json.loads(unit.objective)
    assert second.submitted_attempt
    assert repair_binding.base_ref == "m" * 40
    assert repair_binding.base_sha == "m" * 40
    assert objective["repair_mode"] == "repair_previous_candidate"
    assert objective["previous_candidate"]["source"] == invalid
    assert objective["previous_candidate"]["assessment"]["issues"]
    assert objective["authoring_contract"]["required_test_count"] == 1


@pytest.mark.asyncio
async def test_repair_preserves_source_after_candidate_parse_rejection():
    invalid = plain_catalog_candidate(
        body=(
            '    "unsupported expression statement"\n'
            "    catalog = Catalog()\n"
            "    assert catalog\n"
        ),
    )
    repaired = plain_catalog_candidate()
    service, gateway, _reasoning, _reader = components(
        [
            accepted("catalog-ticket--scenario-draft-1", "u" * 40, "draft-1"),
            accepted("catalog-ticket--scenario-draft-2", "v" * 40, "draft-2"),
        ],
        [approval("SRC-CATALOG")],
        {"u" * 40: invalid, "v" * 40: repaired},
    )

    first = await service.draft(request("catalog"), binding())
    second = await service.submit_candidate(request("catalog"), binding())

    attempt = first.state.attempts[0]
    unit, repair_binding = gateway.calls[1]
    objective = json.loads(unit.objective)
    assert attempt.status == "candidate_invalid"
    assert attempt.candidate_source == invalid
    assert "Test-function docstrings are not permitted" in attempt.feedback
    assert second.submitted_attempt
    assert repair_binding.base_ref == "u" * 40
    assert repair_binding.base_sha == "u" * 40
    assert objective["previous_candidate"]["source"] == invalid


@pytest.mark.asyncio
async def test_repair_fails_closed_when_persisted_candidate_ref_does_not_match_sha():
    store = MemoryStateStore()
    source = plain_catalog_candidate()
    service, _gateway, _reasoning, reader = components([], [], {"p" * 40: source}, store)
    state = __import__("core.development.scenario_drafting", fromlist=["_initial_state"])._initial_state(request("catalog"))
    first = __import__("core.development.scenario_drafting_domain", fromlist=["ScenarioDraftAttempt"]).ScenarioDraftAttempt(
        1, "catalog-ticket--scenario-draft-1", "draft-1", "p" * 40, "evidence/draft-1.json",
        "candidate_invalid", "remove the helper", candidate_source=source, candidate_branch="wrong-ref",
    )
    store.save(__import__("dataclasses").replace(state, attempts=(first,)))
    reader.resolve = lambda ref: "q" * 40

    with pytest.raises(ValueError, match="does not resolve"):
        await service.submit_candidate(request("catalog"), binding())


@pytest.mark.parametrize(
    "source, code",
    [
        ('"""doc"""\nfrom catalog import Catalog\n\ndef test_catalog():\n    assert Catalog\n', "module_docstring"),
        ('from catalog import Catalog\n\n@pytest.fixture\ndef data():\n    return Catalog\n\ndef test_catalog(data):\n    assert data\n', "fixture"),
        ("from catalog import Catalog\n\n@pytest.mark.parametrize('x', [1])\ndef test_catalog(x):\n    assert Catalog\n", "parameterized_test"),
        ('from catalog import Catalog\n\nasync def test_catalog():\n    assert Catalog\n', "async_test"),
    ],
)
def test_adapter_assessment_reports_typed_strict_grammar_violations(source, code):
    from core.development.microcycle_domain import ScenarioSourceCandidate
    from core.development.scenario_drafting import _authoring_contract
    from core.development.scenario_drafting_domain import ScenarioCandidateAssessmentRequest

    proposal = request("catalog")
    candidate_value = ScenarioSourceCandidate(
        proposal.scenario_id, proposal.ticket.step_id, proposal.language_id, proposal.allowed_test_path,
        source, proposal.ticket.test_name, "r" * 40, "evidence/r.json",
    )
    assessment = PythonPytestAdapter().assess_candidate(ScenarioCandidateAssessmentRequest(candidate_value, proposal.ticket.production_path, _authoring_contract(proposal)))

    assert code in {item.code for item in assessment.issues}



def test_test_function_docstring_has_typed_span_and_feedback():
    from core.development.microcycle_domain import ScenarioSourceCandidate
    from core.development.scenario_drafting import _authoring_contract
    from core.development.scenario_drafting_domain import ScenarioCandidateAssessmentRequest

    proposal = request("catalog")
    source = "from catalog import Catalog\n\ndef test_catalog():\n    \"documented\"\n    assert Catalog\n"
    candidate_value = ScenarioSourceCandidate(proposal.scenario_id, proposal.ticket.step_id, proposal.language_id, proposal.allowed_test_path, source, proposal.ticket.test_name, "r" * 40, "evidence/r.json")
    assessment = PythonPytestAdapter().assess_candidate(ScenarioCandidateAssessmentRequest(candidate_value, proposal.ticket.production_path, _authoring_contract(proposal)))
    issue = next(item for item in assessment.issues if item.code == "test_function_docstring")
    assert issue.source_span is not None and issue.source_span.start_line == 4
    assert "test_catalog" in issue.detail and "Remove the standalone string literal" in issue.detail


@pytest.mark.asyncio
async def test_unchanged_repair_consumes_attempt_and_preserves_diagnostics():
    invalid = plain_catalog_candidate(body='    "docstring"\n    assert Catalog\n')
    service, gateway, _reasoning, _reader = components(
        [accepted("catalog-ticket--scenario-draft-1", "u" * 40, "draft-1"), accepted("catalog-ticket--scenario-draft-2", "u" * 40, "draft-2")],
        [], {"u" * 40: invalid},
    )
    first = await service.draft(request("catalog"), binding())
    second = await service.submit_candidate(request("catalog"), binding())
    attempt = second.state.attempts[-1]
    assert first.state.attempts[0].status == "candidate_invalid"
    assert attempt.status == "candidate_unchanged"
    assert attempt.unchanged_evidence is not None
    assert attempt.unchanged_evidence.disposition == "same_revision_and_source"
    assert {item.code for item in attempt.candidate_assessment.issues} >= {"candidate_unchanged", "test_function_docstring"}
    assert "The repair produced no test-source change." in attempt.feedback
    assert len(gateway.calls) == 2


def test_scenario_attempt_persists_worker_provenance():
    from core.development.scenario_drafting_domain import ScenarioDraftAttempt
    from core.development.work_unit import WorkerExecutionProvenance

    provenance = WorkerExecutionProvenance("local-coder", "implementer-tester", "jcode", "eqaq-v2-local-coder", "local-coder", "gpu-2060", "jcode", "direct")
    attempt = ScenarioDraftAttempt(1, "draft-1", "change-1", "a" * 40, "evidence/1", "candidate_submitted", worker_provenance=provenance)
    assert ScenarioDraftAttempt.from_dict(attempt.to_dict()).worker_provenance == provenance



def test_contract_explicitly_prohibits_all_docstring_and_string_expression_forms():
    contract = __import__("core.development.scenario_drafting", fromlist=["_authoring_contract"])._authoring_contract(request("catalog"))
    prohibited = set(contract.prohibited_top_level_forms) | set(contract.prohibited_test_forms)
    assert {"module docstrings", "test-function docstrings", "standalone string-expression statements"} <= prohibited


def test_standalone_string_expression_is_precisely_diagnosed():
    from core.development.microcycle_domain import ScenarioSourceCandidate
    from core.development.scenario_drafting import _authoring_contract
    from core.development.scenario_drafting_domain import ScenarioCandidateAssessmentRequest

    proposal = request("catalog")
    source = "from catalog import Catalog\n\ndef test_catalog():\n    value = Catalog()\n    \"not a docstring\"\n    assert value\n"
    candidate_value = ScenarioSourceCandidate(proposal.scenario_id, proposal.ticket.step_id, proposal.language_id, proposal.allowed_test_path, source, proposal.ticket.test_name, "s" * 40, "evidence/s.json")
    assessment = PythonPytestAdapter().assess_candidate(ScenarioCandidateAssessmentRequest(candidate_value, proposal.ticket.production_path, _authoring_contract(proposal)))
    issue = next(item for item in assessment.issues if item.code == "standalone_string_expression")
    assert issue.source_span is not None and issue.source_span.start_line == 5
    assert "test_catalog" in issue.detail


@pytest.mark.asyncio
async def test_different_revision_with_identical_source_is_a_consumed_noop():
    invalid = plain_catalog_candidate(body='    "docstring"\n    assert Catalog\n')
    service, _gateway, _reasoning, _reader = components(
        [accepted("catalog-ticket--scenario-draft-1", "u" * 40, "draft-1"), accepted("catalog-ticket--scenario-draft-2", "v" * 40, "draft-2")],
        [], {"u" * 40: invalid, "v" * 40: invalid},
    )
    await service.draft(request("catalog"), binding())
    outcome = await service.submit_candidate(request("catalog"), binding())
    evidence = outcome.state.attempts[-1].unchanged_evidence
    assert evidence is not None and evidence.disposition == "same_source"


@pytest.mark.asyncio
async def test_noop_repairs_cannot_create_a_fifth_tester_attempt():
    invalid = plain_catalog_candidate(body='    "docstring"\n    assert Catalog\n')
    results = [accepted(f"catalog-ticket--scenario-draft-{number}", "u" * 40, f"draft-{number}") for number in range(1, 5)]
    service, gateway, _reasoning, _reader = components(results, [], {"u" * 40: invalid})
    for _ in range(4):
        await service.draft(request("catalog"), binding())
    terminal = await service.draft(request("catalog"), binding())
    assert terminal.state.status == ScenarioDraftStatus.ATTEMPTS_EXHAUSTED.value
    assert len(gateway.calls) == 4


@pytest.mark.asyncio
async def test_unselected_timeout_is_an_external_blocker_without_consuming_submission():
    service, gateway, _reasoning, _reader = components(
        [WorkUnitExecutionResult("catalog-ticket--scenario-draft-1", False, "failed", "draft-1", error="executor unavailable timeout")],
        [], {},
    )

    outcome = await service.submit_candidate(request("catalog"), binding())

    assert outcome.state.status == ScenarioDraftStatus.SCENARIO_HARNESS_FAILURE.value
    assert outcome.state.attempts == ()
    assert len(gateway.calls) == 1

@pytest.mark.asyncio
async def test_intent_protocol_failure_preserves_structurally_accepted_candidate_without_tester_retry():
    source = plain_catalog_candidate()
    service, gateway, reasoning, _reader = components(
        [accepted("catalog-ticket--scenario-draft-1", "z" * 40, "draft-1")],
        ["not json", "still not json"], {"z" * 40: source},
    )
    outcome = await service.draft(request("catalog"), binding())
    resumed = await service.draft(request("catalog"), binding())
    attempt = outcome.state.attempts[0]
    assert outcome.state.status == ScenarioDraftStatus.INTENT_PROTOCOL_FAILURE.value
    assert attempt.status == "intent_review_protocol_failure"
    assert attempt.candidate_assessment is not None and attempt.candidate_assessment.accepted
    assert attempt.candidate_source == source
    assert attempt.intent_protocol_failure is not None
    assert attempt.intent_review_response_attempts == 2
    assert len(gateway.calls) == 1 and len(reasoning.requests) == 2
    assert resumed.state == outcome.state


@pytest.mark.asyncio
async def test_one_bounded_json_fence_is_accepted_for_intent_review():
    value, gateway, reasoning, _reader = components(
        [accepted("catalog-ticket--scenario-draft-1", "w" * 40, "draft-1")],
        ["```json" + chr(10) + approval("SRC-CATALOG") + chr(10) + "```"],
        {"w" * 40: plain_catalog_candidate()},
    )
    outcome = await value.draft(request("catalog"), binding())
    assert outcome.approved
    assert len(gateway.calls) == 1 and len(reasoning.requests) == 1
    assert outcome.state.attempts[0].intent_review_response_attempts == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("invalid", [
    json.dumps({"disposition": "unexpected", "feedback": "detail", "evidence_refs": ["SRC-CATALOG"]}),
    json.dumps({"disposition": "approved", "feedback": "", "evidence_refs": ["SRC-CATALOG"]}),
])
async def test_invalid_intent_schema_is_a_typed_protocol_failure(invalid):
    service, gateway, reasoning, _reader = components(
        [accepted("catalog-ticket--scenario-draft-1", "x" * 40, "draft-1")],
        [invalid, invalid], {"x" * 40: plain_catalog_candidate()},
    )
    outcome = await service.draft(request("catalog"), binding())
    assert outcome.state.status == ScenarioDraftStatus.INTENT_PROTOCOL_FAILURE.value
    assert outcome.state.attempts[0].candidate_assessment is not None
    assert outcome.state.attempts[0].candidate_assessment.accepted
    assert outcome.state.attempts[0].intent_protocol_failure is not None
    assert len(gateway.calls) == 1 and len(reasoning.requests) == 2

@pytest.mark.asyncio
async def test_empty_non_latch_candidate_is_typed_as_structural_no_test_and_can_be_repaired():
    service, gateway, reasoning, _reader = components(
        [accepted("catalog-ticket--scenario-draft-1", "q" * 40, "draft-1")],
        [], {"q" * 40: ""},
    )

    outcome = await service.draft(request("catalog"), binding())
    attempt = outcome.state.attempts[0]

    assert attempt.status == "candidate_invalid"
    assert attempt.candidate_assessment is not None
    assert "no_test" in {issue.code for issue in attempt.candidate_assessment.issues}
    assert attempt.candidate_source == ""
    assert gateway.calls and reasoning.requests == []


@pytest.mark.asyncio
async def test_four_selected_no_candidate_submissions_are_consumed_from_canonical_base():
    results = [
        WorkUnitExecutionResult(
            f"catalog-ticket--scenario-draft-{number}", False, "failed", f"draft-{number}",
            selected_worker_id="local-coder", error="Tool 'grep' is not allowed",
        )
        for number in range(1, 5)
    ]
    service, gateway, _reasoning, _reader = components(results, [], {})
    outcomes = [await service.submit_candidate(request("catalog"), binding()) for _ in range(4)]
    terminal = await service.submit_candidate(request("catalog"), binding())

    state = outcomes[-1].state
    assert [item.attempt_number for item in state.attempts] == [1, 2, 3, 4]
    assert state.status == ScenarioDraftStatus.ATTEMPTS_EXHAUSTED.value
    assert terminal.submitted_attempt is False
    assert len(gateway.calls) == 4
    assert [item.repair_mode for item in state.attempts] == [
        "fresh_draft",
        "fresh_retry_after_no_candidate",
        "fresh_retry_after_no_candidate",
        "fresh_retry_after_no_candidate",
    ]
    assert all(item.no_candidate_outcome == "disallowed_or_unknown_tool_call" for item in state.attempts)
    assert all(item.selected_worker_id == "local-coder" for item in state.attempts)
    assert all(call[1].base_sha == "a" * 40 for call in gateway.calls)
