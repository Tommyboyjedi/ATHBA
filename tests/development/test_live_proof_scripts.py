from scripts.run_pr17_independent_reservation_book import build_live_reasoning_gateway as build_proof_gateway
from scripts.run_specification_gatekeeper_probe import build_live_reasoning_gateway as build_probe_gateway
from core.development.behavior_contract_coordinator import CoordinatorDependencies
from core.development.python_test_runtime import PythonPytestRuntime
from core.development.specification_gatekeeper import SpecificationGapTddAdapter, SpecificationGatekeeper
from core.execution.rack_ai_contract import RepositoryBinding


class _DummyExecutionGateway:
    async def execute(self, work_unit, repository_binding):  # pragma: no cover - not called
        raise AssertionError("execute should not be called in this wiring test")


def test_live_proof_gateways_use_provider_retry_policy(monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("OPENAI_API_BASE", "http://127.0.0.1:8017/v1")
    monkeypatch.delenv("OPENAI_ORG", raising=False)

    proof_gateway = build_proof_gateway("local-primary")
    probe_gateway = build_probe_gateway("local-primary")

    assert proof_gateway.delegate.provider.policy.timeout == 300.0
    assert proof_gateway.delegate.provider.policy.max_retries == 1
    assert proof_gateway.delegate.provider.policy.backoff_factor == 2.0
    assert proof_gateway.delegate.model == "local-primary"

    assert probe_gateway.delegate.provider.policy.timeout == 300.0
    assert probe_gateway.delegate.provider.policy.max_retries == 1
    assert probe_gateway.delegate.provider.policy.backoff_factor == 2.0
    assert probe_gateway.delegate.model == "local-primary"


def test_pr17_proof_coordinator_dependencies_include_gatekeeper(monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("OPENAI_API_BASE", "http://127.0.0.1:8017/v1")
    gateway = build_proof_gateway("local-primary")
    runtime = PythonPytestRuntime("/srv/ATHBA/.venv/bin/python")

    dependencies = CoordinatorDependencies(
        execution_gateway=_DummyExecutionGateway(),
        reasoning_gateway=gateway,
        repository_binding=RepositoryBinding(
            repository_id="proof-project",
            base_ref="main",
            base_sha="a" * 40,
            registered_root="/tmp/proof-project",
            environment_resources=[],
        ),
        gatekeeper=SpecificationGatekeeper(gateway),
        gap_adapter=SpecificationGapTddAdapter(),
    )

    assert isinstance(dependencies.gatekeeper, SpecificationGatekeeper)
    assert isinstance(dependencies.gap_adapter, SpecificationGapTddAdapter)
    assert runtime.pytest_command("tests/test_reservation_book.py")
