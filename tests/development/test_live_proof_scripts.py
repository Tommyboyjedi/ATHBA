from scripts.run_specification_gatekeeper_probe import build_live_reasoning_gateway as build_probe_gateway
from core.development.python_test_runtime import PythonPytestRuntime


def test_live_probe_gateway_uses_provider_retry_policy(monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("OPENAI_API_BASE", "http://127.0.0.1:8017/v1")
    monkeypatch.delenv("OPENAI_ORG", raising=False)

    probe_gateway = build_probe_gateway("local-primary")

    assert probe_gateway.delegate.provider.policy.timeout == 300.0
    assert probe_gateway.delegate.provider.policy.max_retries == 1
    assert probe_gateway.delegate.provider.policy.backoff_factor == 2.0
    assert probe_gateway.delegate.model == "local-primary"


def test_python_runtime_command_fixture_remains_available() -> None:
    runtime = PythonPytestRuntime("/srv/ATHBA/.venv/bin/python")
    assert runtime.pytest_command("tests/test_reservation_book.py")
