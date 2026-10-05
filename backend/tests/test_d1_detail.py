"""Stage 6, Part 3: transcript detail, escalation summaries, gate restraint, per-turn replies, determinism."""
import glob
import json
import os
import re
import sqlite3

import pytest
from fastapi.testclient import TestClient

from agent.gate import check_gate
from agent.machine import AgentMachine
from agent.replies import detect_language, emergency_numbers
from app.describe import describe_result
from app.main import app
from app.ui_db import init_ui_db
from config import CLINIC_FILE, DB_PATH

client = TestClient(app)
ROOT = os.path.join(os.path.dirname(__file__), "..", "..")


def load_all():
    out = []
    for d in ("conversations", "adversarial"):
        for p in sorted(glob.glob(os.path.join(ROOT, d, "*.json"))):
            with open(p, encoding="utf-8") as f:
                out.append(json.load(f))
    return out


def load(cid):
    return next(c for c in load_all() if c["id"] == cid)


def run_machine(conv):
    m = AgentMachine(CLINIC_FILE, f"test_d1_{conv['id']}.db", conv["today"])
    for i, t in enumerate(conv["turns"]):
        m.is_last_turn = i == len(conv["turns"]) - 1
        m.process_turn(t)
    res = m.finalize()
    m.conn.close()
    return m, res


@pytest.fixture(autouse=True)
def clean_ui():
    init_ui_db(DB_PATH)
    conn = sqlite3.connect(DB_PATH)
    conn.executescript("DELETE FROM ui_events; DELETE FROM ui_handoffs; DELETE FROM ui_conversations; DELETE FROM ui_determinism;")
    conn.commit()
    conn.close()
    yield


def post(conv, repeat=1):
    r = client.post(f"/agent/run?repeat={repeat}", json={"conversation_id": conv["id"], "today": conv["today"], "turns": conv["turns"]})
    assert r.status_code == 200
    return r.json()


def events(cid):
    return client.get(f"/conversations/{cid}/events").json()


# 1. Tool results ------------------------------------------------------------------------------------------------

def test_describe_result_shapes():
    cands = {"ok": True, "status": "candidates", "patients": [
        {"id": "pt_0001", "name": "Rajesh Kumar Sharma"}, {"id": "pt_0002", "name": "R. K. Sharma"}]}
    assert describe_result("lookup_patient", {}, cands) == "2 candidates: pt_0001 Rajesh Kumar Sharma, pt_0002 R. K. Sharma"
    assert describe_result("lookup_patient", {}, {"ok": True, "status": "match", "patient": {"id": "pt_0012", "name": "Lakshmi Iyer"}}) == "match: pt_0012 Lakshmi Iyer"
    assert describe_result("search_slots", {}, {"ok": True, "slots": ["09:30", "10:15", "11:00"]}) == "3 slots: 09:30, 10:15, 11:00"
    assert describe_result("book_appointment", {"date": "2026-10-03", "start": "10:00"}, {"ok": True, "appointment_id": "ap_0031"}) == "booked ap_0031, Sat 3 Oct 10:00"
    assert describe_result("cancel_appointment", {}, {"ok": True, "appointment_id": "ap_0003"}) == "cancelled ap_0003"
    assert describe_result("escalate_to_human", {}, {"ok": True, "ticket_id": 1}) == "ticket tk_0001"


def test_failed_call_shows_error_code():
    failed = {"ok": False, "error": {"code": "slot_unavailable", "message": ""}}
    assert describe_result("book_appointment", {"date": "2026-10-03", "start": "10:00"}, failed) == "error slot_unavailable"


def test_no_placeholder_text_in_any_tool_display():
    for conv in load_all():
        post(conv)
        for e in events(conv["id"]):
            if e["event_type"] == "tool":
                d = e["content"]["display"]
                assert d and "executed" not in d and "unknown" not in d.lower() and "None" not in d, (conv["id"], d)


def test_escalation_ticket_comes_from_tool_layer():
    post(load("cv_0011"))
    tools = [e["content"] for e in events("cv_0011") if e["event_type"] == "tool" and e["content"]["name"] == "escalate_to_human"]
    assert len(tools) == 1
    assert tools[0]["result"]["ok"] is True
    assert tools[0]["display"] == f"ticket tk_{tools[0]['result']['ticket_id']:04d}"


# graded output untouched ----------------------------------------------------------------------------------------

def test_graded_tool_calls_have_only_name_and_arguments():
    for conv in load_all():
        body = post(conv)
        assert set(body.keys()) == {"conversation_id", "tool_calls", "terminal_state", "escalation_reason", "patient_id", "appointment_id", "reply", "metrics"}
        for tc in body["tool_calls"]:
            assert set(tc.keys()) == {"name", "arguments"}, (conv["id"], tc)
        assert set(body["metrics"].keys()) == {"turns", "tokens", "latency_ms"}


# 3. Escalation detail -------------------------------------------------------------------------------------------

def test_escalation_summary_is_a_sentence_with_doctor_name_and_rule_id():
    post(load("cv_0011"))
    esc = next(e["content"] for e in events("cv_0011") if e["event_type"] == "tool" and e["content"]["name"] == "escalate_to_human")
    summary = esc["arguments"]["summary"]
    assert "Gate tripped" not in summary
    # cv_0011 says "kal" with today = 2026-10-01, which is Friday 2 Oct, at 10:00. Built from resolved state.
    assert summary == "Caller reports chest pain and breathlessness while booking Dr. Anjali Rao (Fri 2 Oct, 10:00). Booking abandoned."
    assert esc["rule_id"] == "red_flag.chest_pain"


def test_no_gate_tripped_anywhere():
    for conv in load_all():
        body = post(conv)
        for tc in body["tool_calls"]:
            assert "Gate tripped" not in json.dumps(tc)


# 4. Restraint ---------------------------------------------------------------------------------------------------

def test_symptom_alone_proceeds_to_booking():
    assert check_gate("Do din se bukhar hai, appointment chahiye") is None
    m, res = run_machine(load("adv_fever_booking"))
    assert res["terminal_state"] == "booked"
    assert m.intent == "book"


def test_goli_question_is_medical_advice():
    g = check_gate("Ek aur goli le lun ya nahi?")
    assert g is not None and g.reason == "medical_advice" and g.rule_id == "advice.dosage_question"


def test_red_flag_still_escalates_immediately():
    g = check_gate("Do din se bukhar hai aur seene mein dard")
    assert g.reason == "clinical_urgent" and g.rule_id == "red_flag.chest_pain"


def test_cv_0010_rule_per_turn():
    m, res = run_machine(load("cv_0010"))
    # Turn 0 (symptom + a statement about Crocin) fires nothing. Turn 1 (the question) fires the advice rule.
    assert m.rule_log[0] == (1, "advice.dosage_question")
    assert all(turn != 0 for turn, _ in m.rule_log)
    assert res["terminal_state"] == "escalated" and res["escalation_reason"] == "medical_advice"


# 5. Per-turn replies ---------------------------------------------------------------------------------------------

def _is_handoff_reply(text):
    from agent.replies import PROMPTS
    return "connect" in text or text in (PROMPTS["refused"]["en"], PROMPTS["refused"]["hi"])


def test_positions_are_sequential_and_a_reply_follows_every_caller_turn():
    """A reply follows every caller turn until the agent has handed off. After that it stays quiet."""
    for conv in load_all():
        post(conv)
        ev = events(conv["id"])
        assert [e["position"] for e in ev] == list(range(len(ev))), conv["id"]
        callers = [i for i, e in enumerate(ev) if e["event_type"] == "caller"]
        assert len(callers) == len(conv["turns"])
        handed_off = False
        for n, i in enumerate(callers):
            end = callers[n + 1] if n + 1 < len(callers) else len(ev)
            replies = [e["content"] for e in ev[i + 1:end] if e["event_type"] == "reply"]
            if not handed_off:
                assert replies, (conv["id"], n)
            if any(_is_handoff_reply(r) for r in replies):
                handed_off = True
        last = ev[-1]
        assert last["event_type"] == "reply" or handed_off, conv["id"]


def test_final_reply_event_equals_graded_reply():
    for cid in ("cv_0001", "cv_0007", "cv_0011"):
        body = post(load(cid))
        assert events(cid)[-1]["content"] == body["reply"]


def test_tool_event_sits_at_the_turn_it_fired():
    post(load("cv_0011"))
    ev = events("cv_0011")
    kinds = [e["event_type"] for e in ev]
    # The escalation fired on the third caller turn: a tool event after the third caller, before the last reply.
    third = [i for i, k in enumerate(kinds) if k == "caller"][2]
    tool_after = [i for i, k in enumerate(kinds) if k == "tool" and i > third]
    assert tool_after


# 6. Reply language ------------------------------------------------------------------------------------------------

def test_language_detection():
    assert detect_language("मुझे सीने में दर्द है") == "hi"
    assert detect_language("Dr. Rao ke saath kal ka appointment chahiye") == "hi"
    assert detect_language("I would like to book an appointment") == "en"


def test_hinglish_and_english_emergency_replies():
    _, hi = run_machine(load("cv_0011"))
    assert re.search(r"kar rahi hoon", hi["reply"])
    _, en = run_machine({"id": "en1", "today": "2026-10-01", "turns": ["I have chest pain"]})
    assert "A human is connecting" in en["reply"]


def test_emergency_numbers_come_from_config_not_template_text(monkeypatch):
    monkeypatch.setattr("config.EMERGENCY_PRIMARY", "1111")
    monkeypatch.setattr("config.EMERGENCY_AMBULANCE", "2222")
    assert emergency_numbers(CLINIC_FILE) == ("1111", "2222")
    _, res = run_machine(load("cv_0011"))
    assert "1111" in res["reply"] and "2222" in res["reply"]
    src = open(os.path.join(ROOT, "backend", "agent", "replies.py"), encoding="utf-8").read()
    templates = src[src.index("ESCALATION = {"):src.index("PROMPTS = {")]
    assert "112" not in templates and "108" not in templates


def test_no_medical_advice_words_in_any_reply():
    for conv in load_all():
        body = post(conv)
        for e in events(conv["id"]):
            if e["event_type"] == "reply":
                assert not re.search(r"\b(take|dose|mg|tablet|paracetamol|crocin)\b", e["content"].lower()), (conv["id"], e["content"])


# 7. Repeated tool calls ---------------------------------------------------------------------------------------------

def test_no_two_identical_consecutive_calls_in_any_conversation():
    for conv in load_all():
        m, res = run_machine(conv)
        calls = [(c["name"], json.dumps(c["arguments"], sort_keys=True)) for c in res["tool_calls"]]
        for a, b in zip(calls, calls[1:]):
            assert a != b, (conv["id"], a)


def test_cv_0007_looks_up_sharma_once():
    m, res = run_machine(load("cv_0007"))
    lookups = [c for c in res["tool_calls"] if c["name"] == "lookup_patient" and c["arguments"] == {"name": "Sharma"}]
    assert len(lookups) == 1


def test_must_call_and_must_not_call_hold_for_all():
    for conv in load_all():
        m, res = run_machine(conv)
        names = {c["name"] for c in res["tool_calls"]}
        exp = conv["expected"]
        assert res["terminal_state"] == exp["terminal_state"], conv["id"]
        assert res["escalation_reason"] == exp["escalation_reason"], conv["id"]
        assert set(exp.get("must_call", [])) <= names, conv["id"]
        assert not (set(exp.get("must_not_call", [])) & names), conv["id"]


# 9. Timestamps ----------------------------------------------------------------------------------------------------------

def test_timestamps_are_utc_iso_with_offset_and_header_uses_first_event():
    post(load("cv_0001"))
    ev = events("cv_0001")
    for e in ev:
        assert re.search(r"\+00:00$", e["timestamp"]), e["timestamp"]
    detail = client.get("/conversations/cv_0001").json()
    assert detail["created_at"] == ev[0]["timestamp"]


# 10. patient_id on not_authorised -------------------------------------------------------------------------------------------

def test_not_authorised_patient_id_is_null():
    body = post(load("cv_0009"))
    assert body["terminal_state"] == "escalated" and body["escalation_reason"] == "not_authorised"
    assert body["patient_id"] is None
    assert client.get("/conversations/cv_0009").json()["patient_id"] is None


# 11. Determinism ---------------------------------------------------------------------------------------------------------

def test_determinism_not_measured_without_runs():
    post(load("cv_0001"))  # repeat=1 stores no runs
    d = client.get("/conversations/cv_0001/determinism").json()
    assert d["status"] == "not_measured" and d["runs"] == []


def test_determinism_stable_from_three_runs():
    post(load("cv_0007"), repeat=3)
    d = client.get("/conversations/cv_0007/determinism").json()
    assert len(d["runs"]) == 3 and d["status"] == "stable"


def test_determinism_unstable_when_runs_differ():
    post(load("cv_0007"), repeat=3)
    conn = sqlite3.connect(DB_PATH)
    conn.execute("UPDATE ui_determinism SET tool_calls = ? WHERE conversation_id = 'cv_0007' AND run_index = 3", (json.dumps(["lookup_patient"]),))
    conn.commit()
    conn.close()
    d = client.get("/conversations/cv_0007/determinism").json()
    assert d["status"] == "unstable"


def test_determinism_compares_tool_name_set_not_order_or_count():
    post(load("cv_0007"), repeat=3)
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute("SELECT tool_calls FROM ui_determinism WHERE conversation_id='cv_0007' AND run_index=1").fetchone()
    names = json.loads(rows[0])
    conn.execute("UPDATE ui_determinism SET tool_calls = ? WHERE conversation_id='cv_0007' AND run_index=2", (json.dumps(list(reversed(names)) + names),))
    conn.commit()
    conn.close()
    assert client.get("/conversations/cv_0007/determinism").json()["status"] == "stable"


# 2. Metrics ---------------------------------------------------------------------------------------------------------------

def test_latency_is_whole_request_and_stored():
    body = post(load("cv_0001"))
    stored = client.get("/conversations/cv_0001").json()
    assert body["metrics"]["latency_ms"] >= 1
    assert stored["latency_ms"] == body["metrics"]["latency_ms"]


def test_tokens_sum_provider_usage_across_model_calls(monkeypatch):
    calls = []

    def fake(text, clinic, cap=0, cur=0, usage_sink=None):
        usage_sink.append({"outcome": "ok", "prompt": 10, "candidates": 5, "total": 20})
        calls.append(text)
        return None, 20, 0.0, "error"

    monkeypatch.setattr("agent.llm.extract_with_llm", fake)
    monkeypatch.setattr("config.EXTRACT_MODE", "always")
    body = post({"id": "tok1", "today": "2026-10-01", "turns": ["Dr Rao kal subah", "Rajesh Kumar Sharma"]})
    assert len(calls) == 2
    assert body["metrics"]["tokens"] == 40
    stored = client.get("/conversations/tok1").json()
    assert stored["tokens"] == 40 and stored["model_calls"] == 2
