"""Stage 4 rule fixes: intent is not defaulted to book, ambiguous dates are not
resolved silently, and the model never overrides a rule result."""
from types import SimpleNamespace

import pytest

from agent.machine import AgentMachine, run_agent_rules
from agent.normalise import extract_intent, date_is_ambiguous, normalise_date
from config import CLINIC_FILE

TODAY = "2026-10-01"


@pytest.fixture
def machine(tmp_path):
    return AgentMachine(CLINIC_FILE, str(tmp_path / "m.db"), TODAY)


# --- 1. Intent default ------------------------------------------------------

@pytest.mark.parametrize("text", [
    "Shanivaar subah, 3 tareekh.",   # only a date and a time
    "Subah 10 baje.",                # only a time
    "kal",                           # only a date
])
def test_turn_with_no_intent_wording_gives_none(text):
    assert extract_intent(text) is None


def test_turn_with_only_a_name_gives_none():
    assert extract_intent("Main Harpreet Singh, number 9812200311.") is None


def test_intent_book_is_kept_across_turns(machine):
    machine.process_turn("Dr. Rao ke saath appointment chahiye.")
    assert machine.intent == "book"
    machine.process_turn("Shanivaar subah, 3 tareekh.")
    assert machine.intent == "book"


def test_explicit_cancel_overrides_book(machine):
    machine.process_turn("Dr. Rao ke saath appointment chahiye.")
    machine.process_turn("Actually cancel karna hai.")
    assert machine.intent == "cancel"


def test_model_other_intent_is_not_an_intent(machine, monkeypatch):
    fake = SimpleNamespace(intent=SimpleNamespace(value="other"), doctor=None, date_phrase=None,
                           time_phrase=None, patient_name=None, phone=None)
    monkeypatch.setattr("config.EXTRACT_MODE", "always")
    monkeypatch.setattr("agent.llm.extract_with_llm", lambda *a, **k: (fake, 0, 0.0, None))
    machine.process_turn("Hello?")
    assert machine.intent is None


def test_model_intent_never_overrides_existing_intent(machine, monkeypatch):
    machine.process_turn("Dr. Rao ke saath appointment chahiye.")
    fake = SimpleNamespace(intent=SimpleNamespace(value="reschedule"), doctor=None, date_phrase=None,
                           time_phrase=None, patient_name=None, phone=None)
    monkeypatch.setattr("config.EXTRACT_MODE", "always")
    monkeypatch.setattr("agent.llm.extract_with_llm", lambda *a, **k: (fake, 0, 0.0, None))
    machine.process_turn("Budhwar kar dijiye.")
    assert machine.intent == "book"


# --- 2. Ambiguous dates -----------------------------------------------------

def test_kal_ya_parso_is_ambiguous():
    assert date_is_ambiguous("Kal ya parso, jo mil jaye.")


def test_ya_phir_form_is_ambiguous():
    assert date_is_ambiguous("kal ya phir parso")


@pytest.mark.parametrize("text", ["parso", "kal", "Shanivaar", "kal ya kal"])
def test_single_date_is_not_ambiguous(text):
    assert not date_is_ambiguous(text)


def test_parso_alone_resolves_to_2026_10_03():
    assert normalise_date("parso", TODAY) == "2026-10-03"


def test_kal_alone_resolves_to_2026_10_02():
    assert normalise_date("kal", TODAY) == "2026-10-02"


def test_ambiguous_date_is_not_resolved(machine):
    machine.process_turn("Dr. Rao ke saath appointment chahiye.")
    machine.process_turn("Kal ya parso, jo mil jaye.")
    assert machine.date is None
    assert machine.date_ambiguous is True


def test_ambiguous_date_asks_once_and_books_nothing():
    conv = {"id": "amb_1", "today": TODAY, "turns": [
        "Dr. Rao ke saath appointment chahiye.",
        "Kal ya parso, jo mil jaye.",
    ]}
    res = run_agent_rules(conv, CLINIC_FILE, "amb_1.db")
    called = {c["name"] for c in res["tool_calls"]}
    assert "book_appointment" not in called
    assert res["terminal_state"] == "abandoned"
    assert "kal ya parso" in res["reply"].lower() or "tareekh" in res["reply"].lower()


# --- Model failures on unparsed turns ---------------------------------------

@pytest.mark.parametrize("err", ["rate_limited", "error"])
def test_transient_model_failure_does_not_escalate(err, monkeypatch):
    conv = {"id": f"tr_{err}", "today": TODAY, "turns": ["Hello?"]}
    monkeypatch.setattr("config.EXTRACT_MODE", "auto")
    monkeypatch.setattr("agent.llm.extract_with_llm", lambda *a, **k: (None, 0, 0.0, err))
    res = run_agent_rules(conv, CLINIC_FILE, f"tr_{err}.db")
    assert res["terminal_state"] == "abandoned"
    assert res["escalation_reason"] is None


def test_malformed_model_output_still_escalates(monkeypatch):
    conv = {"id": "bad_json", "today": TODAY, "turns": ["Hello?"]}
    monkeypatch.setattr("config.EXTRACT_MODE", "auto")
    monkeypatch.setattr("agent.llm.extract_with_llm", lambda *a, **k: (None, 0, 0.0, "invalid"))
    res = run_agent_rules(conv, CLINIC_FILE, "bad_json.db")
    assert res["terminal_state"] == "escalated"
    assert res["escalation_reason"] == "out_of_scope"


# --- 3. Model reconciliation ------------------------------------------------

def _model_says(date_phrase):
    return SimpleNamespace(intent=None, doctor=None, date_phrase=date_phrase,
                           time_phrase=None, patient_name=None, phone=None)


def test_model_does_not_replace_a_date_the_rules_filled(machine, monkeypatch):
    monkeypatch.setattr("config.EXTRACT_MODE", "always")
    monkeypatch.setattr("agent.llm.extract_with_llm", lambda *a, **k: (_model_says("kal"), 0, 0.0, None))
    machine.process_turn("Parso ko Dr. Rao ke saath appointment chahiye.")
    assert machine.date == "2026-10-03"


def test_model_fills_a_date_the_rules_left_empty(machine, monkeypatch):
    monkeypatch.setattr("config.EXTRACT_MODE", "always")
    monkeypatch.setattr("agent.llm.extract_with_llm", lambda *a, **k: (_model_says("kal"), 0, 0.0, None))
    machine.process_turn("Dr. Rao ke saath appointment chahiye.")
    assert machine.date == "2026-10-02"


def test_model_cannot_fill_an_ambiguous_date(machine, monkeypatch):
    monkeypatch.setattr("config.EXTRACT_MODE", "always")
    monkeypatch.setattr("agent.llm.extract_with_llm", lambda *a, **k: (_model_says("parso"), 0, 0.0, None))
    machine.process_turn("Kal ya parso, jo mil jaye.")
    assert machine.date is None
