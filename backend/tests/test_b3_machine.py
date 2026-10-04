import pytest
import glob
import json
import os
from agent.machine import run_agent_rules, AgentMachine
from config import CLINIC_FILE
def get_convs():
    conv_dir = os.path.join(os.path.dirname(__file__), "../../conversations")
    convs = []
    for filepath in glob.glob(os.path.join(conv_dir, "*.json")):
        with open(filepath, "r", encoding="utf-8") as f:
            convs.append(json.load(f))
    return convs
def test_all_15_scripts_rules_only():
    for conv in get_convs():
        db_path = f"test_{conv['id']}.db"
        res = run_agent_rules(conv, CLINIC_FILE, db_path)
        if os.path.exists(db_path): os.remove(db_path)
        expected = conv["expected"]
        assert res["terminal_state"] == expected["terminal_state"], f"Failed state for {conv['id']}"
        assert res["escalation_reason"] == expected["escalation_reason"], f"Failed reason for {conv['id']}"
        called = set(call["name"] for call in res["tool_calls"])
        for tool in expected.get("must_call", []): assert tool in called, f"{conv['id']} missing must_call {tool}"
        for tool in expected.get("must_not_call", []): assert tool not in called, f"{conv['id']} illegally called {tool}"
def test_determinism_three_runs():
    for conv in get_convs():
        db_path = f"test_det_{conv['id']}.db"
        results = []
        for _ in range(3):
            res = run_agent_rules(conv, CLINIC_FILE, db_path)
            if os.path.exists(db_path): os.remove(db_path)
            results.append((res["terminal_state"], res["escalation_reason"], tuple(sorted(set(c["name"] for c in res["tool_calls"])))))
        assert results[0] == results[1] == results[2], f"Determinism failed for {conv['id']}"
def test_latch_position():
    for conv in get_convs():
        turns = conv["turns"]
        for pos in range(len(turns) + 1):
            test_turns = list(turns)
            test_turns.insert(pos, "I have severe chest pain!")
            mod_conv = dict(conv)
            mod_conv["turns"] = test_turns
            db_path = f"test_latch_{conv['id']}_{pos}.db"
            res = run_agent_rules(mod_conv, CLINIC_FILE, db_path)
            if os.path.exists(db_path): os.remove(db_path)
            assert res["terminal_state"] == "escalated", f"Latch failed for {conv['id']} pos {pos}"
            assert res["escalation_reason"] == "clinical_urgent"
            write_tools = {"book_appointment", "reschedule_appointment", "cancel_appointment"}
            called = set(call["name"] for call in res["tool_calls"])
            assert not (called & write_tools), f"Write tools called after latch in {conv['id']} pos {pos}"
def test_reply_postcheck():
    machine = AgentMachine(CLINIC_FILE, "dummy.db", "2026-10-01")
    machine.terminal_state = "booked"
    machine.tool_calls = [{"name": "book_appointment", "arguments": {"appointment_id": "ap_1234"}}]
    reply1 = machine.postcheck_reply("Your appointment ap_1234 is booked.", "FALLBACK")
    assert "ap_1234" in reply1
    reply2 = machine.postcheck_reply("Your appointment ap_9999 is booked.", "FALLBACK")
    assert reply2 == "FALLBACK"
def test_no_invented_slots():
    machine = AgentMachine(CLINIC_FILE, "dummy.db", "2026-10-01")
    machine.terminal_state = "abandoned"
    machine.tool_calls = [{"name": "search_slots", "arguments": {}, "result": {"slots": ["10:00", "10:15"]}}]
    reply1 = machine.postcheck_reply("Slots available at 10:00 and 10:15", "FALLBACK")
    assert "10:00" in reply1
    reply2 = machine.postcheck_reply("Slots available at 11:30", "FALLBACK")
    assert reply2 == "FALLBACK"
def test_name_grounding():
    machine = AgentMachine(CLINIC_FILE, "dummy.db", "2026-10-01")
    machine.terminal_state = "abandoned"
    machine.tool_calls = [{"name": "lookup_patient", "result": {"ok": True, "patient": {"name": "Priya Nair"}}}]
    reply1 = machine.postcheck_reply("Hello Priya Nair.", "FALLBACK")
    assert reply1 != "FALLBACK"
    reply2 = machine.postcheck_reply("Hello Rajesh Kumar Sharma.", "FALLBACK")
    assert reply2 == "FALLBACK"
def test_emergency_reply_content():
    machine = AgentMachine(CLINIC_FILE, "dummy.db", "2026-10-01")
    machine.terminal_state = "escalated"
    machine.escalation_reason = "clinical_urgent"
    res = machine.finalize()
    assert "human is connecting" in res["reply"].lower()
    assert "if symptoms are severe or worsening" in res["reply"].lower()
    assert "call the emergency number now" in res["reply"].lower()
    assert "112" in res["reply"]
    assert "108" in res["reply"]
    advice_words = ["dose", "dawai", "goli", "medicine", "pill", "crocin"]
    for w in advice_words:
        assert w not in res["reply"].lower()
