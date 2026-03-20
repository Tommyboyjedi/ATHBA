import json
import time

import httpx
import pytest

from core.llm.contracts.exceptions import ValidationError
from core.llm.providers.openai_provider import OpenAIProvider


@pytest.fixture
def schema():
    with open("core/llm/schemas/pm_intent_schema.json") as f:
        return json.load(f)


@pytest.fixture(autouse=True)
def env(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")


def test_openai_provider_happy_path(schema, monkeypatch):
    payload = {
        "response": "ok",
        "intent": "greet",
        "agents_routing": [],
        "entities": {},
    }
    api_response = {
        "output": [
            {
                "content": [{"text": json.dumps(payload)}],
            }
        ],
        "usage": {"input_tokens": 5, "output_tokens": 7},
    }
    url = "https://api.openai.com/v1/responses"

    def fake_post(url, headers, json, timeout):
        return httpx.Response(200, json=api_response, request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx, "post", fake_post)

    provider = OpenAIProvider()
    result = provider.invoke("hi", model="gpt", response_schema=schema)

    assert json.loads(result.text) == payload
    assert result.usage == {"input_tokens": 5, "output_tokens": 7}
    assert result.raw == api_response


def test_openai_provider_retries_on_429_then_succeeds(schema, monkeypatch):
    payload = {
        "response": "ok",
        "intent": "greet",
        "agents_routing": [],
        "entities": {},
    }
    api_response = {
        "output": [
            {
                "content": [{"text": json.dumps(payload)}],
            }
        ],
        "usage": {"input_tokens": 1, "output_tokens": 1},
    }

    url = "https://api.openai.com/v1/responses"
    responses = [
        httpx.Response(429, request=httpx.Request("POST", url)),
        httpx.Response(200, json=api_response, request=httpx.Request("POST", url)),
    ]

    def fake_post(url, headers, json, timeout):
        return responses.pop(0)

    monkeypatch.setattr(httpx, "post", fake_post)
    monkeypatch.setattr(time, "sleep", lambda *_: None)

    provider = OpenAIProvider(max_retries=2)
    result = provider.invoke("hi", model="gpt", response_schema=schema)
    assert json.loads(result.text)["intent"] == "greet"
    assert result.usage == {"input_tokens": 1, "output_tokens": 1}


def test_openai_provider_schema_violation(monkeypatch, schema):
    bad_payload = {"response": "oops"}  # missing required fields
    api_response = {
        "output": [
            {
                "content": [{"text": json.dumps(bad_payload)}],
            }
        ],
        "usage": {"input_tokens": 1, "output_tokens": 1},
    }

    def fake_post(url, headers, json, timeout):
        return httpx.Response(200, json=api_response, request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx, "post", fake_post)

    provider = OpenAIProvider()
    with pytest.raises(ValidationError):
        provider.invoke("hi", model="gpt", response_schema=schema)
