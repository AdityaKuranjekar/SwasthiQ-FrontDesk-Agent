import pytest
import glob
import json
import os
from agent.machine import run_agent_rules
from config import CLINIC_FILE

def get_fixtures():
    conv_dir = os.path.join(os.path.dirname(__file__), "fixtures")
    convs = []
    for filepath in glob.glob(os.path.join(conv_dir, "*.json")):
        with open(filepath, "r", encoding="utf-8") as f:
            convs.append(json.load(f))
    return convs

def test_holdout_fixtures():
    for conv in get_fixtures():
        db_path = f"test_{conv['id']}.db"
        res = run_agent_rules(conv, CLINIC_FILE, db_path)
        if os.path.exists(db_path): os.remove(db_path)
        expected = conv["expected"]
        assert res["terminal_state"] == expected["terminal_state"], f"Failed state for {conv['id']}. Got {res['terminal_state']}, expected {expected['terminal_state']}"
        assert res["escalation_reason"] == expected["escalation_reason"], f"Failed reason for {conv['id']}"
        called = set(call["name"] for call in res["tool_calls"])
        for tool in expected.get("must_call", []): assert tool in called, f"{conv['id']} missing must_call {tool}"
        for tool in expected.get("must_not_call", []): assert tool not in called, f"{conv['id']} illegally called {tool}"

def test_mutation_swapped_names():
    temp_clinic = 'temp_clinic_mutation.json'
    with open(CLINIC_FILE, 'r', encoding='utf-8') as f:
        data = json.load(f)

    for p in data['patients']:
        if p['id'] == 'pt_0016': p['name'] = 'Kabir Joshi'
        elif p['id'] == 'pt_0031': p['name'] = 'Neha Bhatt'

    with open(temp_clinic, 'w', encoding='utf-8') as f:
        json.dump(data, f)
        
    conv = {
        "id": "mut_001",
        "today": "2026-10-01",
        "turns": [
            "Kabir Joshi, 9812200404.",
            "Mera appointment cancel karna hai."
        ],
        "expected": {
            "terminal_state": "cancelled",
            "escalation_reason": None,
            "must_call": ["cancel_appointment"]
        }
    }
    
    db_path = f"test_mut.db"
    res = run_agent_rules(conv, temp_clinic, db_path)
    if os.path.exists(db_path): os.remove(db_path)
    if os.path.exists(temp_clinic): os.remove(temp_clinic)
    
    assert res["terminal_state"] == "cancelled"
    assert res["appointment_id"] == "ap_0006"
