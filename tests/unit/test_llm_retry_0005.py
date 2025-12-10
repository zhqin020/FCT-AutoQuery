import json

import pytest

import fct_analysis.llm as llm


class FakeResp:
    def __init__(self, text, status=200):
        self._text = text
        self.status_code = status

    def raise_for_status(self):
        if not (200 <= self.status_code < 300):
            raise Exception(f"status {self.status_code}")

    def json(self):
        try:
            return json.loads(self._text)
        except Exception:
            return {"text": self._text}


def test_extract_entities_with_retries(monkeypatch):
    calls = {"n": 0}

    def fake_post(url, json=None, timeout=None):
        calls["n"] += 1
        # Fail twice, succeed third
        if calls["n"] < 3:
            raise Exception("connection reset")
        return FakeResp('{"visa_office": "TestCity", "judge": "Justice X"}', status=200)

    monkeypatch.setattr(llm, "requests", __import__("types").SimpleNamespace(post=fake_post))

    res = llm.extract_entities_with_ollama("some text", retries=3, backoff=0.01, timeout=1)
    assert res["visa_office"] == "TestCity"
    assert res["judge"] == "Justice X"


def test_requests_missing_raises():
    # Simulate requests missing
    monkey = __import__("pytest").MonkeyPatch()
    monkey.setattr(llm, "requests", None)
    with pytest.raises(ConnectionError):
        llm.extract_entities_with_ollama("foo")
    monkey.undo()
