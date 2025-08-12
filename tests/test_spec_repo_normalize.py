import asyncio
from core.datastore.repos.spec_version_repo import SpecVersionRepo

def test_normalize_plaintext_to_json():
    repo = SpecVersionRepo()
    data = repo._normalize_content("hello world")
    assert isinstance(data, dict)
    assert "sections" in data
    assert data["sections"][0]["body"] == "hello world"

def test_normalize_json_string_passthrough():
    repo = SpecVersionRepo()
    s = '{"a": 1, "b": 2}'
    data = repo._normalize_content(s)
    assert data["a"] == 1
    assert data["b"] == 2

def test_normalize_dict_passthrough():
    repo = SpecVersionRepo()
    d = {"sections": [{"name": "x", "body": "y"}]}
    data = repo._normalize_content(d)
    assert data is d
