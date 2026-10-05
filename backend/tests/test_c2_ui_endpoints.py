import pytest
from fastapi.testclient import TestClient
import json
import sqlite3
import os
from app.main import app
from app.ui_db import init_ui_db
from config import DB_PATH

client = TestClient(app)

@pytest.fixture(autouse=True)
def setup_db():
    init_ui_db(DB_PATH)
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.executescript("""
        DELETE FROM ui_events;
        DELETE FROM ui_handoffs;
        DELETE FROM ui_conversations;
        DELETE FROM ui_determinism;
    """)
    conn.commit()
    conn.close()
    yield

def load_cv(cv_name):
    path = os.path.join(os.path.dirname(__file__), '..', '..', 'conversations', f'{cv_name}.json')
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)

def test_events_order_cv_0001():
    data = load_cv("cv_0001")
    req = {
        "conversation_id": "cv_0001",
        "today": data["today"],
        "turns": data["turns"]
    }
    resp = client.post("/agent/run", json=req)
    assert resp.status_code == 200
    
    events_resp = client.get("/conversations/cv_0001/events")
    assert events_resp.status_code == 200
    events = events_resp.json()
    
    assert len(events) > 0
    # Must contain caller turn, tool call, and agent reply
    types = [e["event_type"] for e in events]
    assert "caller" in types
    assert "tool" in types
    assert "reply" in types
    
    # Check ordering: caller pos < tool pos < reply pos
    caller_pos = [e["position"] for e in events if e["event_type"] == "caller"]
    reply_pos = [e["position"] for e in events if e["event_type"] == "reply"]
    assert max(caller_pos) < max(reply_pos)
    
    search_tools = [e for e in events if e["event_type"] == "tool" and e["content"]["name"] == "search_slots"]
    if search_tools:
        tool_content = search_tools[0]["content"]
        assert "slots" in tool_content["display"]


def test_clinical_urgent_handoff_cv_0011():
    data = load_cv("cv_0011")
    req = {
        "conversation_id": "cv_0011",
        "today": data["today"],
        "turns": data["turns"]
    }
    resp = client.post("/agent/run", json=req)
    assert resp.status_code == 200
    
    handoffs_resp = client.get("/handoffs?status=open")
    assert handoffs_resp.status_code == 200
    handoffs = handoffs_resp.json()
    
    # Verify handoff
    urgent = [h for h in handoffs if h["conversation_id"] == "cv_0011"]
    assert len(urgent) == 1
    h = urgent[0]
    assert h["escalation_reason"] == "clinical_urgent"
    assert h["resolved"] == 0
    
    # "with the raw caller text" - it escalated on turn 2
    assert "seene" in h["caller_said"].lower() or "dard" in h["caller_said"].lower()

def test_get_handoffs_all_and_open():
    data = load_cv("cv_0011")
    req = {"conversation_id": "c1", "today": data["today"], "turns": data["turns"]}
    client.post("/agent/run", json=req)
    
    assert len(client.get("/handoffs?status=open").json()) == 1
    assert len(client.get("/handoffs?status=all").json()) == 1

def test_handoffs_summary():
    data = load_cv("cv_0001")
    req = {"conversation_id": "s1", "today": data["today"], "turns": data["turns"]}
    client.post("/agent/run", json=req)
    
    res = client.get(f"/handoffs/summary?date={data['today']}")
    assert res.status_code == 200
    body = res.json()
    assert body["total_conversations"] >= 1
    
    # 422 case
    res_422 = client.get("/handoffs/summary?date=invalid-date")
    assert res_422.status_code == 422

def test_resolve_handoff_404_409():
    data = load_cv("cv_0011")
    req = {"conversation_id": "r1", "today": data["today"], "turns": data["turns"]}
    client.post("/agent/run", json=req)
    
    # 404
    assert client.post("/handoffs/unknown/resolve", json={"resolved_by": "User", "note": "test"}).status_code == 404
    
    # Resolve
    res = client.post("/handoffs/r1/resolve", json={"resolved_by": "User", "note": "Resolved it"})
    assert res.status_code == 200
    
    # 409
    res2 = client.post("/handoffs/r1/resolve", json={"resolved_by": "User", "note": "Again"})
    assert res2.status_code == 409

def test_conversations_endpoints():
    data = load_cv("cv_0001")
    today = data["today"]
    req = {"conversation_id": "conv1", "today": today, "turns": data["turns"]}
    client.post("/agent/run", json=req)
    
    # List
    lst = client.get(f"/conversations?date={today}")
    assert lst.status_code == 200
    assert len(lst.json()) >= 1
    assert lst.json()[0]["conversation_id"] == "conv1"
    
    # 422
    assert client.get("/conversations?date=bad").status_code == 422
    
    # Get one
    one = client.get("/conversations/conv1")
    assert one.status_code == 200
    assert one.json()["conversation_id"] == "conv1"
    
    # 404
    assert client.get("/conversations/unknown").status_code == 404
    assert client.get("/conversations/unknown/events").status_code == 404
    assert client.get("/conversations/unknown/determinism").status_code == 404

def test_determinism_endpoint():
    data = load_cv("cv_0001")
    req = {"conversation_id": "det1", "today": data["today"], "turns": data["turns"]}
    client.post("/agent/run?repeat=3", json=req)
    
    det = client.get("/conversations/det1/determinism")
    assert det.status_code == 200
    body = det.json()
    assert len(body["runs"]) == 3
    assert body["stable"] is True

def test_contract_all_15_scripts():
    import glob
    files = glob.glob(os.path.join(os.path.dirname(__file__), "..", "..", "conversations", "cv_*.json"))
    assert len(files) == 15
    for f in files:
        with open(f, "r", encoding="utf-8") as file:
            data = json.load(file)
            req = {
                "conversation_id": os.path.basename(f).replace(".json", ""),
                "today": data["today"],
                "turns": data["turns"]
            }
            res = client.post("/agent/run", json=req)
            assert res.status_code == 200
            body = res.json()
            assert "conversation_id" in body
            assert "terminal_state" in body
            assert "reply" in body
            assert "metrics" in body
            
            # Additional assertion: the UI tables were populated without crashing
            events_resp = client.get(f"/conversations/{req['conversation_id']}/events")
            assert events_resp.status_code == 200







def test_cors_headers():
    res1 = client.options("/agent/run", headers={"Origin": "http://localhost:5173", "Access-Control-Request-Method": "POST"})
    assert res1.headers.get("access-control-allow-origin") == "http://localhost:5173"
    
    res2 = client.options("/agent/run", headers={"Origin": "http://example.com", "Access-Control-Request-Method": "POST"})
    assert res2.headers.get("access-control-allow-origin") is None
