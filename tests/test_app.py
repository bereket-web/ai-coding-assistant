from __future__ import annotations

from fastapi.testclient import TestClient

import codepilot.app as service
from codepilot.app import app

client = TestClient(app)


def test_python_rules_flag_mutable_default_bare_except_eval_and_none_comparison() -> None:
    code = """def f(items=[]):
    eval('1 + 1')
    if items == None:
        try:
            return items
        except:
            return []
"""
    response = client.post("/api/analyze", json={"task": "bugs", "code": code})
    assert response.status_code == 200
    data = response.json()
    rules = {finding["rule"] for finding in data["findings"]}
    assert {"PY101", "PY102", "PY104", "PY105"}.issubset(rules)
    assert data["mode"] == "offline heuristic"
    assert data["code_was_executed"] is False
    assert "not a proof of defects" in data["result"]


def test_syntax_error_is_returned_as_structured_finding() -> None:
    data = client.post("/api/analyze", json={"task": "bugs", "code": "def broken(:\n pass"}).json()
    assert data["facts"]["parseable"] is False
    assert data["findings"][0]["rule"] == "PY001"
    assert data["findings"][0]["severity"] == "error"


def test_summary_lists_structure_without_claiming_semantics() -> None:
    response = client.post(
        "/api/analyze",
        json={
            "task": "summarize",
            "code": "import math\nclass Solver:\n    def solve(self, n):\n        return math.sqrt(n)",
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert "Solver" in data["result"] and "solve" in data["result"] and "math" in data["result"]
    assert data["facts"]["classes"] == ["Solver"]
    assert data["facts"]["functions"] == ["solve"]
    assert "does not infer behavior" in data["result"]


def test_test_task_emits_explicitly_skipped_scaffold() -> None:
    data = client.post(
        "/api/analyze", json={"task": "tests", "code": "def add(left, right):\n    return left + right"}
    ).json()
    assert "pytest.skip" in data["result"]
    assert "not evidence" in data["result"]


def test_other_language_is_not_claimed_to_be_parsed() -> None:
    data = client.post(
        "/api/analyze", json={"language": "JavaScript", "code": "function f(x) { return x; }"}
    ).json()
    assert data["facts"]["parseable"] is False
    assert data["findings"] == []
    assert "does not parse this language" in data["result"]


def test_code_is_never_executed_by_endpoint(tmp_path) -> None:
    marker = tmp_path / "should_not_exist.txt"
    code = f"open({str(marker)!r}, 'w').write('executed')"
    response = client.post("/api/analyze", json={"task": "explain", "code": code})
    assert response.status_code == 200
    assert response.json()["code_was_executed"] is False
    assert not marker.exists()


def test_input_limits_and_invalid_task_are_rejected() -> None:
    assert client.post("/api/analyze", json={"task": "what", "code": "x"}).status_code == 422
    assert client.post("/api/analyze", json={"code": "x" * 24_001}).status_code == 422
    assert client.post("/api/analyze", json={"code": "x", "context": "c" * 3_001}).status_code == 422


def test_missing_provider_falls_back_to_offline_result(monkeypatch) -> None:
    monkeypatch.delenv("CODEPILOT_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    data = client.post("/api/analyze", json={"code": "x = 1", "use_model": True}).json()
    assert data["mode"] == "offline heuristic"
    assert "No provider key" in data["warning"]


def test_configured_model_is_called_only_when_explicitly_selected(monkeypatch) -> None:
    async def fake_model(task: str, code: str, language: str, context: str) -> str:
        return "Draft review; verify before use."

    monkeypatch.setattr(service, "model_is_configured", lambda: True)
    monkeypatch.setattr(service, "ask_model", fake_model)
    data = client.post("/api/analyze", json={"code": "x = 1", "use_model": True}).json()
    assert data["mode"] == "configured model"
    assert data["result"].startswith("Draft review")
    assert "may be incorrect" in data["warning"]


def test_provider_error_falls_back_without_echoing_details(monkeypatch) -> None:
    async def broken_model(task: str, code: str, language: str, context: str) -> str:
        raise RuntimeError("private-provider-diagnostic")

    monkeypatch.setattr(service, "model_is_configured", lambda: True)
    monkeypatch.setattr(service, "ask_model", broken_model)
    data = client.post("/api/analyze", json={"code": "x = 1", "use_model": True}).json()
    assert data["mode"] == "offline heuristic"
    assert "private-provider-diagnostic" not in data["warning"]
    assert "Model request failed" in data["warning"]


def test_health_reports_model_unavailable_without_credentials(monkeypatch) -> None:
    monkeypatch.delenv("CODEPILOT_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    response = client.get("/health")
    assert response.json()["status"] == "ok"
    assert response.json()["model_available"] is False
