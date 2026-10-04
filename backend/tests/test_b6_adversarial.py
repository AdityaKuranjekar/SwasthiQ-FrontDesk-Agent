import pytest
import glob
import json
import os
from agent.machine import run_agent_rules
from config import CLINIC_FILE

def get_adv():
    conv_dir = os.path.join(os.path.dirname(__file__), "../../adversarial")
    convs = []
    for filepath in glob.glob(os.path.join(conv_dir, "*.json")):
        with open(filepath, "r", encoding="utf-8") as f:
            convs.append(json.load(f))
    return convs

def test_adversarial_fixtures():
    for conv in get_adv():
        db_path = f"test_{conv['id']}.db"
        res = run_agent_rules(conv, CLINIC_FILE, db_path)
        if os.path.exists(db_path): os.remove(db_path)
        expected = conv["expected"]
        assert res["terminal_state"] == expected["terminal_state"], f"Failed state for {conv['id']}"
        assert res["escalation_reason"] == expected["escalation_reason"], f"Failed reason for {conv['id']}"
        called = set(call["name"] for call in res["tool_calls"])
        for tool in expected.get("must_call", []): assert tool in called, f"{conv['id']} missing must_call {tool}"
        for tool in expected.get("must_not_call", []): assert tool not in called, f"{conv['id']} illegally called {tool}"

