import os
import glob
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_agent_run_stub():
    response = client.post("/agent/run", json={
        "conversation_id": "test_cv",
        "today": "2026-10-01",
        "turns": ["Hello"]
    })
    assert response.status_code == 200
    data = response.json()
    assert data["conversation_id"] == "test_cv"
    assert data["terminal_state"] == "abandoned"
    assert data["tool_calls"] == []

def test_no_llm_imports_in_tools():
    tools_dir = os.path.join(os.path.dirname(__file__), "..", "tools")
    for filepath in glob.glob(os.path.join(tools_dir, "*.py")):
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()
            assert "anthropic" not in content.lower(), f"LLM SDK found in {filepath}"
            assert "openai" not in content.lower(), f"LLM SDK found in {filepath}"
            assert "llm" not in content.lower(), f"LLM usage found in {filepath}"

