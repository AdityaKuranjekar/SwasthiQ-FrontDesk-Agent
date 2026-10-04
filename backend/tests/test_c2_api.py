import pytest
from fastapi.testclient import TestClient
from app.main import app
import glob
import json
import os
from unittest.mock import patch
from config import CLINIC_FILE

client = TestClient(app)

def get_convs():
    conv_dir = os.path.join(os.path.dirname(__file__), "../../conversations")
    convs = []
    for filepath in glob.glob(os.path.join(conv_dir, "*.json")):
        with open(filepath, "r", encoding="utf-8") as f:
            convs.append(json.load(f))
    return convs

def test_contract_fields_present():
    convs = get_convs()
    for conv in convs:
        resp = client.post("/agent/run", json={
            "conversation_id": conv["id"],
            "today": conv["today"],
            "turns": conv["turns"]
        })
        assert resp.status_code == 200, f"Failed for {conv['id']}"
        data = resp.json()
        assert "conversation_id" in data
        assert "tool_calls" in data
        assert "terminal_state" in data
        assert "escalation_reason" in data
        assert "patient_id" in data
        assert "appointment_id" in data
        assert "reply" in data
        assert "metrics" in data
        assert "turns" in data["metrics"]
        assert "tokens" in data["metrics"]
        assert "latency_ms" in data["metrics"]

def test_conversation_id_echoed():
    resp = client.post("/agent/run", json={
        "conversation_id": "test_123",
        "today": "2026-10-01",
        "turns": ["hello"]
    })
    assert resp.status_code == 200
    assert resp.json()["conversation_id"] == "test_123"

def test_bad_json_422():
    resp = client.post("/agent/run", data="not json")
    assert resp.status_code == 422
    assert "detail" in resp.json()

def test_missing_turns_422():
    resp = client.post("/agent/run", json={
        "conversation_id": "test_123",
        "today": "2026-10-01"
    })
    assert resp.status_code == 422

def test_invalid_today_422():
    resp = client.post("/agent/run", json={
        "conversation_id": "test_123",
        "today": "2026-13-40",
        "turns": ["hello"]
    })
    assert resp.status_code == 422

def test_empty_turns_422():
    resp = client.post("/agent/run", json={
        "conversation_id": "test_123",
        "today": "2026-10-01",
        "turns": []
    })
    assert resp.status_code == 422

@patch("app.main.AgentMachine.process_turn")
def test_internal_exception_safe_response(mock_process):
    mock_process.side_effect = Exception("Intentional crash")
    resp = client.post("/agent/run", json={
        "conversation_id": "test_crash",
        "today": "2026-10-01",
        "turns": ["hello"]
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["terminal_state"] == "escalated"
    assert data["escalation_reason"] == "out_of_scope"

@patch("app.main.RATE_LIMIT_PER_MIN", 3)
def test_rate_limit_429():
    import app.main
    app.main.ip_tracking.clear()
    app.main.RATE_LIMIT_PER_MIN = 3
    
    for _ in range(3):
        resp = client.post("/agent/run", json={
            "conversation_id": "test_limit",
            "today": "2026-10-01",
            "turns": ["hello"]
        })
        assert resp.status_code == 200
        
    resp = client.post("/agent/run", json={
        "conversation_id": "test_limit",
        "today": "2026-10-01",
        "turns": ["hello"]
    })
    assert resp.status_code == 429
    assert "detail" in resp.json()
