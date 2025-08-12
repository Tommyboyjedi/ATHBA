import asyncio
import json
from core.datastore.repos.spec_version_repo import SpecVersionRepo, _SpecColProxy

def test_normalize_plaintext_to_json():
    repo = SpecVersionRepo()
    data = repo._normalize_content("hello world")
    assert isinstance(data, dict)
    assert "sections" in data
    assert data["sections"][0]["body"] == "hello world"

def test_normalize_json_string_passthrough():
    repo = SpecVersionRepo()
    s = json.dumps({"sections": [{"name": "raw", "body": "x"}]})
    data = repo._normalize_content(s)
    assert data["sections"][0]["body"] == "x"

def test_normalize_dict_passthrough():
    repo = SpecVersionRepo()
    d = {"sections": [{"name": "x", "body": "y"}]}
    data = repo._normalize_content(d)
    assert data is d

def test_proxy_find_one_converts_json_content_to_html():
    class FakeCol:
        @staticmethod
        async def find_one(*args, **kwargs):
            return {
                "project_id": "p1",
                "version": 1,
                "content": {"sections": [{"name": "raw", "body": "<p>hi</p>"}]},
            }

    proxy = _SpecColProxy(FakeCol())
    loop = asyncio.get_event_loop()
    doc = loop.run_until_complete(proxy.find_one({}))
    assert isinstance(doc.get("content"), str)
    assert doc["content"] == "<p>hi</p>"
