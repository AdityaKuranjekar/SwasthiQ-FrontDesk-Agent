import pytest
from agent.gate import check_gate

def test_pure_dosage():
    # pure dosage question returns medical_advice and not clinical_urgent
    res = check_gate("Crocin ka dose kitna hai")
    assert res is not None and res.kind == "escalated" and res.reason == "medical_advice"

positive_cases = [
    "pet mein bahut dard hai",
    "stomach pain ho raha hai",
    "pait dard hai, appointment chahiye",
    "pet dukh raha hai",
    "petmen dard",
    "pet mein marod hai",
    "dard nahi, lekin pet mein bahut dard hai", # clause test
    "pehle pet dard tha aur abhi bhi ho raha hai", # active marker
    "dard nahi, lekin seene mein bahut dard", # red flag
]

@pytest.mark.parametrize("phrase", positive_cases)
def test_stomach_positives(phrase):
    res = check_gate(phrase)
    assert res is not None and res.kind == "escalated" and res.reason == "clinical_urgent"

negative_cases = [
    ("pet dard nahi hai, appointment chahiye", None),
    ("pehle pet dard tha, ab theek hai", None),
    ("bukhar hai, sardi hai", None),
    ("Crocin ka dose kitna hai", "medical_advice")
]

@pytest.mark.parametrize("phrase, expected_reason", negative_cases)
def test_stomach_negatives(phrase, expected_reason):
    res = check_gate(phrase)
    if expected_reason is None:
        assert res is None
    else:
        assert res is not None and res.reason == expected_reason
        
def test_booking_stopped_on_urgent():
    # A test that a clinical_urgent turn stops booking even when the same turn asks for an appointment
    from agent.machine import AgentMachine
    from config import CLINIC_FILE
    import sqlite3
    
    machine = AgentMachine(CLINIC_FILE, 'test_stop.db', '2026-10-01')
    machine.process_turn("Mujhe aaj subah Dr Rao ka appointment chahiye, pet mein bahut dard hai.")
    
    assert machine.terminal_state == "escalated"
    assert machine.escalation_reason == "clinical_urgent"
    # Ensure no tools were called except escalate
    # In my AgentMachine, escalate is called when terminal_state is set, but since it's gate, it's immediate
    # Actually book_appointment should NOT be in tool_calls
    call_names = [c["name"] for c in machine.tool_calls]
    assert "book_appointment" not in call_names
    assert "escalate_to_human" in call_names
