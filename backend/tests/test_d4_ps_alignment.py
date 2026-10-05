"""What the PS Conversation Detail screen implies, checked on real conversations.

- Every slot the agent tells the caller came from a search_slots result in the same conversation.
- The outcome carries the patient and appointment ids whenever the conversation produced them.
- Tokens and latency stay real for a conversation that used the model, even on a repeat run.
"""
import glob
import hashlib
import json
import os
import re
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
HHMM = re.compile(r"\b\d{2}:\d{2}\b")


def conversations():
    out = []
    for pattern in ("conversations/*.json", "adversarial/*.json", "backend/tests/fixtures/*.json"):
        for path in sorted(glob.glob(os.path.join(ROOT, pattern))):
            with open(path, encoding="utf-8") as f:
                out.append(json.load(f))
    return out


def run(conv):
    body = client.post("/agent/run", json={"conversation_id": conv["id"], "today": conv["today"], "turns": conv["turns"]})
    assert body.status_code == 200
    events = client.get(f"/conversations/{conv['id']}/events").json()
    return body.json(), events


def by_id(cid):
    return next(c for c in conversations() if c["id"] == cid)


def test_all_conversations_are_found():
    assert len(conversations()) >= 23


@pytest.mark.parametrize("conv", conversations(), ids=lambda c: c["id"])
def test_every_time_the_agent_states_is_grounded(conv):
    """A time in an agent reply must come from a search_slots result, or be the time the caller asked for."""
    from agent.normalise import normalise_time

    body, events = run(conv)
    grounded = set()
    for e in events:
        if e["event_type"] != "tool":
            continue
        call = e["content"]
        if call["name"] == "search_slots":
            grounded |= set((call["result"] or {}).get("slots", []))
        if call["name"] in ("book_appointment", "reschedule_appointment") and (call["result"] or {}).get("ok"):
            grounded.add(call["arguments"].get("start"))
    # The time the caller asked for, in the form the agent normalised it to ("10 baje" -> 10:00).
    grounded |= {t for t in (normalise_time(turn) for turn in conv["turns"]) if t}
    for e in events:
        if e["event_type"] != "reply":
            continue
        for t in HHMM.findall(e["content"]):
            assert t in grounded, f"{conv['id']}: agent said {t}, which no tool returned and the caller did not ask for: {e['content']}"


def test_taken_slot_is_flagged_and_real_alternatives_are_offered():
    body, events = run(by_id("cv_0015"))
    first_reply = next(e["content"] for e in events if e["event_type"] == "reply")
    assert "09:00 khali nahi hai" in first_reply        # ap_0015 holds 09:00 on 8 Oct
    assert "09:15" in first_reply                        # the next free slot in clinic.json


def test_closed_day_says_there_is_no_slot():
    body, events = run(by_id("cv_0005"))
    replies = [e["content"] for e in events if e["event_type"] == "reply"]
    assert all("koi slot khali nahi" in r for r in replies), replies
    assert body["terminal_state"] == "abandoned"


def test_search_runs_when_the_day_becomes_known_not_only_at_the_end():
    _, events = run(by_id("cv_0001"))
    kinds = [(e["event_type"], e["content"]["name"] if e["event_type"] == "tool" else "") for e in events]
    search_at = next(i for i, k in enumerate(kinds) if k == ("tool", "search_slots"))
    book_at = next(i for i, k in enumerate(kinds) if k == ("tool", "book_appointment"))
    assert search_at < book_at - 1
    searches = [k for k in kinds if k == ("tool", "search_slots")]
    assert len(searches) == 1, "the booking must reuse the earlier search, not call it again"


# Outcome fields ---------------------------------------------------------------------------------------------------

def test_booked_conversation_carries_patient_and_appointment():
    body, _ = run(by_id("cv_0001"))
    assert body["terminal_state"] == "booked"
    assert body["patient_id"] == "pt_0013"
    assert body["appointment_id"] and body["appointment_id"].startswith("ap_")


def test_cancelled_conversation_carries_the_cancelled_appointment():
    body, _ = run(by_id("cv_0004"))
    assert body["terminal_state"] == "cancelled"
    assert body["patient_id"] == "pt_0004"
    assert body["appointment_id"] == "ap_0002"


def test_escalation_keeps_the_patient_resolved_before_it():
    """As in the PS mockup: an escalated clinical conversation still reports the patient it had identified."""
    body, _ = run(by_id("cv_h11"))
    assert body["terminal_state"] == "escalated" and body["escalation_reason"] == "clinical_urgent"
    assert body["patient_id"] == "pt_0013"
    assert body["appointment_id"] is None


def test_not_authorised_reports_no_patient():
    body, _ = run(by_id("cv_0009"))
    assert body["escalation_reason"] == "not_authorised"
    assert body["patient_id"] is None and body["appointment_id"] is None


# Tokens and latency -----------------------------------------------------------------------------------------------

def test_a_repeat_run_still_reports_what_the_model_cost(monkeypatch):
    """The first run pays for the model call. A repeat reuses the cached answer (0 now), but the screen must
    keep showing the real cost of the conversation, not fall back to 0 tokens and a tenth of a second."""
    from agent import llm

    turn = "Hello?"
    parsed = SimpleNamespace(intent=None, doctor=None, date_phrase=None, time_phrase=None, patient_name=None, phone=None)
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    llm.clear_llm_cache()
    llm._remember(hashlib.sha256(turn.encode("utf-8")).hexdigest(), parsed, None, 103, 2.0)
    try:
        conv = {"id": "usage_1", "today": "2026-10-01", "turns": [turn]}
        body, _ = run(conv)
        assert body["metrics"]["tokens"] == 0                      # this request cost nothing: cached answer
        stored = client.get("/conversations/usage_1").json()
        assert stored["tokens"] == 103                             # the conversation's real cost
        assert stored["latency_ms"] >= 2000
    finally:
        llm.clear_llm_cache()


def test_a_conversation_with_no_model_call_shows_zero_tokens():
    body, _ = run(by_id("cv_0001"))
    stored = client.get("/conversations/cv_0001").json()
    assert body["metrics"]["tokens"] == 0 and stored["tokens"] == 0
    assert stored["latency_ms"] >= 1
