"""Evidence-level tests for PR30 model and generic execution boundaries."""
from dataclasses import asdict, replace
import json

import pytest

from core.development.athba_workspace_routing import AthbaWorkspaceIdentity
from core.development.post_behavior_assessment import (
    IdentifierRename, NamingAssessmentInput, NamingAssessor, NamingDecision, NamingMaterial,
    RefactorAssessor, RefactorDecision, RefactorOpportunity,
    parse_naming_decision, parse_refactor_decision,
)
from core.development.post_behavior_slice import (
    FocusedProductionSlice, ProductionSliceScope, PythonProductionSlice, SliceRequest,
)
from core.development.project_environment_state import ProjectRuntime, EnvironmentResource
from core.development.post_behavior_workspace import (
    PostBehaviorWorkspaceExecutor, PostBehaviorWorkspaceInput, PostBehaviorWorkspaceRequests,
    opaque_workspace_identity,
)
from core.development.specification_evidence_policy import RevisionFile, SpecificationSnapshot
from core.execution.local_only_post_behavior_reasoning import LocalOnlyPostBehaviorReasoning
from core.execution.provider_reasoning_gateway import ProviderReasoningGateway
from core.execution.rack_ai_request import RepositoryBinding
from core.execution.rack_ai_workspace_connector import RackAiV2WorkspaceSerializer
from core.execution.reasoning_gateway import ReasoningRequest
from core.execution.workspace_execution_port import WorkspaceExecutionResult, WorkspaceExecutionStatus
from core.llm.contracts.provider import NormalizedResult, ProviderRetryPolicy
from core.llm.providers.openai_provider import OpenAIProvider

REVISION = "a" * 40
SOURCE = "def old_name(value):\n    return value + value\n"
REQUIRED = "The callable must be named exact_name."
TEST = "from subject import old_name\n\ndef test_result():\n    assert old_name(2) == 4\n"


@pytest.fixture
def local_provider(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "local-test-only")
    monkeypatch.setenv("OPENAI_API_BASE", "http://127.0.0.1:9999/v1")
    return OpenAIProvider(ProviderRetryPolicy(10, 0, 1))


def production():
    return FocusedProductionSlice(
        REVISION, (RevisionFile("subject.py", SOURCE),),
        ProductionSliceScope("UNRELATED_HISTORY_SENTINEL", "GATEKEEPER_SENTINEL", ("subject.py",)),
    )


def naming_input():
    return NamingAssessmentInput(NamingMaterial(REQUIRED, ("exact_name",)), production())


def reasoner(provider, monkeypatch, response):
    requests = []
    def invoke(request):
        requests.append(request)
        return NormalizedResult(response, {}, {})
    monkeypatch.setattr(provider, "invoke", invoke)
    return LocalOnlyPostBehaviorReasoning(ProviderReasoningGateway(provider, "configured-local")), requests


@pytest.mark.asyncio
async def test_naming_boundary_transmits_exact_focused_material_only(local_provider, monkeypatch):
    gateway, calls = reasoner(local_provider, monkeypatch, "old_name -> exact_name")
    result = await NamingAssessor(gateway).reason(naming_input())
    assert result == NamingDecision(IdentifierRename("old_name", "exact_name"))
    assert len(calls) == 1
    context = json.loads(calls[0].prompt.split("\n", 1)[1])
    assert context == {
        "explicit_behavior_naming": {"text": REQUIRED, "required_identifiers": ["exact_name"]},
        "production": [{"path": "subject.py", "source": SOURCE}],
    }
    assert set(asdict(calls[0])) == {"prompt", "model", "temperature", "max_tokens", "response_schema"}
    assert calls[0].response_schema is None
    assert "SENTINEL" not in calls[0].prompt


@pytest.mark.asyncio
async def test_refactor_boundary_contains_production_only(local_provider, monkeypatch):
    gateway, calls = reasoner(local_provider, monkeypatch, "NO")
    assert await RefactorAssessor(gateway).reason(production()) == RefactorDecision()
    assert len(calls) == 1
    assert json.loads(calls[0].prompt.split("\n", 1)[1]) == {
        "production": [{"path": "subject.py", "source": SOURCE}],
    }
    assert REQUIRED not in calls[0].prompt
    assert TEST not in calls[0].prompt
    assert "SENTINEL" not in calls[0].prompt


@pytest.mark.parametrize("answer", [
    "YES\ncurrent_name: old_name\nrequired_name: exact_name",
    "old_name -> exact_name",
])
def test_one_explicit_identifier_mapping(answer):
    assert parse_naming_decision(answer, naming_input()).rename == IdentifierRename("old_name", "exact_name")


@pytest.mark.parametrize("answer", [
    "YES", "NO because already correct", "old_name -> nicer_name",
    "missing -> exact_name", "exact_name -> exact_name",
    "old_name -> exact_name\nsecond -> third",
    "YES\ncurrent_name: old_name\nrequired_name: exact_name\nreason: stylish",
    '{"current_name":"old_name","required_name":"exact_name"}',
    "```\nold_name -> exact_name\n```",
])
def test_naming_rejects_multiple_invented_or_wrapped_mapping(answer):
    with pytest.raises(ValueError):
        parse_naming_decision(answer, naming_input())


def test_assessor_no_and_single_refactor_objective():
    assert parse_naming_decision("NO", naming_input()) == NamingDecision()
    assert parse_refactor_decision("NO") == RefactorDecision()
    assert parse_refactor_decision("YES\nobjective: Remove duplicate computation.\nreason: Avoid repeated work.") == (
        RefactorDecision(RefactorOpportunity("Remove duplicate computation.", "Avoid repeated work."))
    )


@pytest.mark.parametrize("answer", [
    "YES", "NO; no opportunity", "YES\nobjective: first\nobjective: second\nreason: brief",
    "YES\nobjective: first\nreason: brief\nextra: leaked",
    "YES\nobjective: \nreason: brief",
    "YES\nobjective: " + "x" * 401 + "\nreason: brief",
    '{"objective":"first","reason":"brief"}',
])
def test_refactor_requires_one_bounded_objective_with_brief_reason(answer):
    with pytest.raises(ValueError):
        parse_refactor_decision(answer)


@pytest.mark.parametrize("endpoint", [
    "https://api.openai.com/v1", "https://openrouter.ai/api/v1",
    "http://127.0.0.1.evil.invalid/v1", "http://10.0.0.1/v1",
    "file:///tmp/local", "http://user@127.0.0.1/v1",
])
def test_cloud_or_unapproved_endpoint_blocked_before_call(local_provider, monkeypatch, endpoint):
    gateway, calls = reasoner(local_provider, monkeypatch, "NO")
    local_provider.settings.api_base = endpoint
    with pytest.raises(ValueError):
        LocalOnlyPostBehaviorReasoning(gateway.gateway)
    assert calls == []


@pytest.mark.asyncio
async def test_local_endpoint_is_rechecked_before_each_invocation(local_provider, monkeypatch):
    gateway, calls = reasoner(local_provider, monkeypatch, "NO")
    local_provider.settings.api_base = "https://cloud.invalid/v1"
    with pytest.raises(ValueError):
        await RefactorAssessor(gateway).reason(production())
    assert calls == []


def test_automatic_provider_retries_are_blocked(local_provider, monkeypatch):
    gateway, calls = reasoner(local_provider, monkeypatch, "NO")
    local_provider.policy = ProviderRetryPolicy(10, 1, 1)
    with pytest.raises(ValueError, match="zero automatic"):
        LocalOnlyPostBehaviorReasoning(gateway.gateway)
    assert calls == []


def test_unknown_gateway_or_fallback_provider_is_not_accepted():
    class FallbackProvider:
        def invoke(self, request):
            raise AssertionError("cloud invocation must never occur")
    with pytest.raises(ValueError, match="direct local"):
        LocalOnlyPostBehaviorReasoning(ProviderReasoningGateway(FallbackProvider(), "unselected"))


@pytest.mark.asyncio
async def test_raw_assessor_evidence_is_retained_before_parse_failure(local_provider, monkeypatch):
    gateway, calls = reasoner(local_provider, monkeypatch, "YES\nmalformed: retain this response")
    records = []
    class Evidence:
        def record(self, record):
            records.append(record)
    gateway = LocalOnlyPostBehaviorReasoning(gateway.gateway, Evidence())
    with pytest.raises(ValueError):
        await RefactorAssessor(gateway).reason(production())
    assert len(calls) == 1
    assert [record.completed for record in records] == [False, True]
    assert records[0].invocation_id == records[1].invocation_id
    assert records[1].result.text == "YES\nmalformed: retain this response"
    assert records[0].request == records[1].request


def workspace_input():
    return PostBehaviorWorkspaceInput(
        opaque_workspace_identity(AthbaWorkspaceIdentity("lane-work", "lane-submission", "lane-attempt")),
        RepositoryBinding("disposable", "accepted", REVISION),
        production(),
        (RevisionFile("tests/test_subject.py", TEST), RevisionFile("tests/test_other.py", "UNRELATED_TEST_SENTINEL")),
        (("python", "-m", "pytest", "tests"),),
    )


def test_exact_rename_request_has_only_focused_source_affected_tests_and_mapping():
    request = PostBehaviorWorkspaceRequests().rename(workspace_input(), IdentifierRename("old_name", "exact_name"))
    assert request.allowed_writable_paths == ("subject.py", "tests/test_subject.py")
    assert json.loads(request.objective.split("\n", 1)[1]) == {
        "identifier_substitution": {"current_name": "old_name", "required_name": "exact_name"},
        "production": [{"path": "subject.py", "source": SOURCE}],
        "affected_tests": [{"path": "tests/test_subject.py", "source": TEST}],
    }
    assert request.repository.base_sha == REVISION
    assert request.acceptance_commands == (("python", "-m", "pytest", "tests"),)
    assert request.network_policy == "disabled"


def test_refactor_request_has_only_one_objective_and_production_tests_not_writable():
    request = PostBehaviorWorkspaceRequests().refactor(
        workspace_input(), RefactorOpportunity("Remove duplicate computation.", "RATIONALE_SENTINEL"),
    )
    assert request.allowed_writable_paths == ("subject.py",)
    assert json.loads(request.objective.split("\n", 1)[1]) == {
        "objective": "Remove duplicate computation.",
        "production": [{"path": "subject.py", "source": SOURCE}],
    }
    assert TEST not in request.objective
    assert "SENTINEL" not in request.objective
    payload = RackAiV2WorkspaceSerializer().serialize(request)
    routing = payload["work_unit"]["routing"]
    assert routing["required_capabilities"] == ["coding"]
    assert routing["priority"] == "low"
    assert payload["work_unit"]["requirements"] == {"complexity": "small", "requires_large_context": False}
    assert payload["work_unit"]["limits"]["max_implementation_attempts"] == 1
    serialized = json.dumps(payload)
    for forbidden in ("Naming Assessor", "Renamer", "Refactor Assessor", "Refactorer",
                      "Gatekeeper", "post_behavior", "worker_id", "model_id", "endpoint",
                      "GPU", "JCode", "SENTINEL"):
        assert forbidden not in serialized


def test_semantic_ids_and_unrelated_resources_cannot_cross_workspace_boundary():
    with pytest.raises(ValueError, match="opaque"):
        replace(workspace_input(), identity=AthbaWorkspaceIdentity("Naming Assessor", "Renamer", "Gatekeeper"))
    with pytest.raises(ValueError, match="unrelated"):
        replace(workspace_input(), repository=RepositoryBinding("disposable", "accepted", REVISION,
                                                                 environment_resources=["architecture.md"]))
    with pytest.raises(ValueError, match="accepted production slice"):
        replace(workspace_input(), repository=RepositoryBinding("disposable", "accepted", "b" * 40))


def test_existing_generic_port_is_used_for_execution_and_recovery():
    input_value = workspace_input()
    request = PostBehaviorWorkspaceRequests().rename(input_value, IdentifierRename("old_name", "exact_name"))
    result = WorkspaceExecutionResult(request.identity, WorkspaceExecutionStatus.ACCEPTED, candidate_revision="b" * 40)
    calls = []
    class Port:
        def submit_workspace_change(self, value):
            calls.append(value)
            return result
        def get_result(self, submission_id):
            assert submission_id == request.identity.submission_id
            return result
        def cancel(self, submission_id):
            raise AssertionError("no implicit cancellation")
    executor = PostBehaviorWorkspaceExecutor(Port())
    assert executor.execute(request) is result
    assert executor.recover(request.identity.submission_id) is result
    assert calls == [request]


def test_authorized_readonly_runtime_resources_survive_generic_serialization():
    runtime = ProjectRuntime(
        "python", "3", "/srv/ATHBA/.venv", ["/srv/ATHBA/.venv/bin/python", "-m", "pytest"],
        environment_resources=[EnvironmentResource("/srv/ATHBA/.venv")],
    )
    input_value = replace(
        workspace_input(), runtime=runtime,
        repository=RepositoryBinding("disposable", "accepted", REVISION,
                                     environment_resources=runtime.resource_paths()),
    )
    request = PostBehaviorWorkspaceRequests().refactor(
        input_value, RefactorOpportunity("Remove duplicate computation.", "Avoid repeated work."),
    )
    payload = RackAiV2WorkspaceSerializer().serialize(request)
    assert payload["work_unit"]["environment_resources"] == ["/srv/ATHBA/.venv"]
    assert request.allowed_writable_paths == ("subject.py",)
    assert "/srv/ATHBA/.venv" not in request.objective


@pytest.mark.asyncio
async def test_provider_error_is_evidenced_without_retry_or_fallback(local_provider, monkeypatch):
    calls, records = [], []
    def invoke(request):
        calls.append(request)
        raise RuntimeError("local provider unavailable")
    class Evidence:
        def record(self, record):
            records.append(record)
    monkeypatch.setattr(local_provider, "invoke", invoke)
    gateway = LocalOnlyPostBehaviorReasoning(
        ProviderReasoningGateway(local_provider, "configured-local"), Evidence(),
    )
    with pytest.raises(RuntimeError, match="local provider unavailable"):
        await RefactorAssessor(gateway).reason(production())
    assert len(calls) == 1
    assert [record.completed for record in records] == [False, True]
    assert records[1].error == "local provider unavailable"
    assert records[1].result is None


@pytest.mark.asyncio
async def test_evidence_start_failure_prevents_model_invocation(local_provider, monkeypatch):
    gateway, calls = reasoner(local_provider, monkeypatch, "NO")
    class Evidence:
        def record(self, record):
            raise OSError("evidence store unavailable")
    gateway = LocalOnlyPostBehaviorReasoning(gateway.gateway, Evidence())
    with pytest.raises(OSError, match="evidence store unavailable"):
        await RefactorAssessor(gateway).reason(production())
    assert calls == []


def test_subclassed_gateway_cannot_hide_cloud_fallback(local_provider):
    class CloudFallback(ProviderReasoningGateway):
        async def reason(self, request):
            raise AssertionError("unapproved gateway must never execute")
    with pytest.raises(ValueError, match="direct local gateway"):
        LocalOnlyPostBehaviorReasoning(CloudFallback(local_provider, "configured-local"))



def test_rename_receives_only_exact_affected_tests_and_required_constants():
    source = (
        "import os\nfrom subject import old_name\n\nEXPECTED = 4\n"
        "UNRELATED = 'UNRELATED_CONSTANT_SENTINEL'\n\n"
        "def test_result():\n    assert old_name(2) == EXPECTED\n\n"
        "def test_unrelated():\n    assert 'UNRELATED_TEST_CASE_SENTINEL' != os.getcwd()\n"
    )
    request = PostBehaviorWorkspaceRequests().rename(
        replace(workspace_input(), accepted_tests=(RevisionFile("tests/test_subject.py", source),)),
        IdentifierRename("old_name", "exact_name"),
    )
    tests = json.loads(request.objective.split("\n", 1)[1])["affected_tests"]
    assert tests == [{"path": "tests/test_subject.py", "source": (
        "from subject import old_name\n\nEXPECTED = 4\n\n"
        "def test_result():\n    assert old_name(2) == EXPECTED\n"
    )}]
    assert "SENTINEL" not in request.objective
    assert "import os" not in request.objective



@pytest.mark.parametrize("source", [
    "def actual():\n    value = 'old_name'\n    return value\n",
    "def actual():\n    old_name = 1\n    return old_name\n",
    "def actual(old_name):\n    return old_name\n",
])
def test_naming_cannot_ground_implemented_name_in_literals_locals_or_parameters(source):
    request = replace(naming_input(), production=replace(
        production(), files=(RevisionFile("subject.py", source),),
    ))
    with pytest.raises(ValueError, match="focused production declarations"):
        parse_naming_decision("old_name -> exact_name", request)


def test_rename_class_test_context_excludes_unrelated_methods_and_their_imports():
    source = (
        "import os\nfrom subject import old_name\n\n"
        "class TestSubject:\n"
        "    def test_unrelated(self):\n"
        "        assert 'UNRELATED_METHOD_SENTINEL' != os.getcwd()\n\n"
        "    def test_result(self):\n"
        "        assert old_name(2) == 4\n"
    )
    request = PostBehaviorWorkspaceRequests().rename(
        replace(workspace_input(), accepted_tests=(RevisionFile("tests/test_subject.py", source),)),
        IdentifierRename("old_name", "exact_name"),
    )
    payload = json.loads(request.objective.split("\n", 1)[1])
    assert payload["affected_tests"] == [{"path": "tests/test_subject.py", "source": (
        "from subject import old_name\n\nclass TestSubject:\n"
        "    def test_result(self):\n        assert old_name(2) == 4\n"
    )}]
    assert "SENTINEL" not in request.objective and "import os" not in request.objective



def test_rename_expands_only_resolved_consumer_references_and_preserves_other_contexts():
    consumer = RevisionFile("consumer.py", (
        "from subject import old_name\n\n"
        "def consume():\n    return old_name(2)\n\n"
        "def unrelated():\n    return 'UNRELATED_CONSUMER_SENTINEL'\n"
    ))
    unrelated = RevisionFile("other.py", "def unrelated_change():\n    return 'OTHER_PRODUCTION_SENTINEL'\n")
    accepted = SpecificationSnapshot(REVISION, (RevisionFile("subject.py", SOURCE), consumer, unrelated))
    before = SpecificationSnapshot("b" * 40, (RevisionFile("subject.py", ""), consumer))
    focused = PythonProductionSlice().derive(SliceRequest(before, accepted))
    assert set(focused.scope.production_paths) == {"subject.py", "other.py"}
    value = replace(workspace_input(), production=focused, rename_reference_sources=accepted)
    request = PostBehaviorWorkspaceRequests().rename(value, IdentifierRename("old_name", "exact_name"))
    assert request.allowed_writable_paths == ("subject.py", "consumer.py", "tests/test_subject.py")
    payload = json.loads(request.objective.split("\n", 1)[1])
    assert payload["production"] == [
        {"path": "subject.py", "source": SOURCE},
        {"path": "consumer.py", "source": (
            "from subject import old_name\n\ndef consume():\n    return old_name(2)\n"
        )},
    ]
    assert "SENTINEL" not in request.objective
    unchanged_input = NamingAssessmentInput(NamingMaterial(REQUIRED, ("exact_name",)), focused)
    assert unchanged_input.production is focused
    refactor = PostBehaviorWorkspaceRequests().refactor(value, RefactorOpportunity("Simplify the calculation.", "Avoid duplication."))
    assert refactor.allowed_writable_paths == ("subject.py", "other.py")
    assert "consumer.py" not in refactor.objective and "UNRELATED_CONSUMER_SENTINEL" not in refactor.objective


def test_repeated_mutable_field_assignments_resolve_one_exact_identifier_change():
    source = (
        "class Counter:\n"
        "    def __init__(self):\n        self.count = 0\n\n"
        "    def reset(self):\n        self.count = 0\n"
    )
    tests = (
        "from subject import Counter\n\n"
        "def test_count():\n    counter = Counter()\n    assert counter.count == 0\n"
    )
    value = replace(workspace_input(), production=replace(
        production(), files=(RevisionFile("subject.py", source),),
    ), accepted_tests=(RevisionFile("tests/test_subject.py", tests),))
    request = PostBehaviorWorkspaceRequests().rename(value, IdentifierRename("count", "total"))
    assert request.allowed_writable_paths == ("subject.py", "tests/test_subject.py")
    payload = json.loads(request.objective.split("\n", 1)[1])
    assert payload["identifier_substitution"] == {"current_name": "count", "required_name": "total"}
    assert "self.count = 0" in payload["production"][0]["source"]
    assert "assert counter.count == 0" in payload["affected_tests"][0]["source"]


@pytest.mark.asyncio
async def test_naming_prompt_limits_mismatch_to_missing_required_identifier(local_provider, monkeypatch):
    gateway, calls = reasoner(local_provider, monkeypatch, "NO")
    request = replace(naming_input(), production=replace(
        production(), files=(RevisionFile("subject.py", SOURCE +
            "\ndef exact_name(value):\n    return old_name(value)\n"),),
    ))
    assert await NamingAssessor(gateway).reason(request) == NamingDecision()
    assert len(calls) == 1
    instruction = calls[0].prompt.split("\n", 1)[0]
    assert "A naming mismatch exists only when an explicitly required identifier is absent" in instruction
    assert "and the same public/product concept is implemented under a different identifier" in instruction
    assert "If the required identifier already exists in production, answer NO." in instruction
    assert "Do not suggest removal of aliases or duplicate helpers" in instruction
    assert "syntax changes, API-shape changes, style improvements, general cleanup or refactoring" in instruction


@pytest.mark.asyncio
async def test_naming_prompt_output_identifiers_have_no_trailing_punctuation(local_provider, monkeypatch):
    gateway, calls = reasoner(local_provider, monkeypatch, "NO")
    await NamingAssessor(gateway).reason(naming_input())
    instruction = calls[0].prompt.split("\n", 1)[0]
    output = instruction.split("Return exactly either: ", 1)[1].split(" Do not add", 1)[0]
    assert output == (
        "NO or: YES\\ncurrent_name: <exact existing identifier>"
        "\\nrequired_name: <exact required identifier>"
    )
    assert "Do not add punctuation, explanation, markdown, or any other text." in instruction


@pytest.mark.parametrize("suffix", [".", ",", ";", "!"])
def test_naming_parser_rejects_punctuation_after_required_total(suffix):
    request = NamingAssessmentInput(
        NamingMaterial("The callable must be named total.", ("total",)),
        replace(production(), files=(RevisionFile("subject.py",
            "def get_total():\n    return 0\n"),)),
    )
    valid = "YES\ncurrent_name: get_total\nrequired_name: total"
    assert parse_naming_decision(valid, request).rename == IdentifierRename("get_total", "total")
    with pytest.raises(ValueError, match="NO or exactly one mapping"):
        parse_naming_decision(valid + suffix, request)
