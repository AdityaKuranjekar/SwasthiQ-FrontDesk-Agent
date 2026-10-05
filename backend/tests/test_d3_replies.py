"""Per-turn agent replies: no repeats, no filler, no contradiction with the tool result on the same turn.

The conversations are loaded by absolute path and the test refuses to pass if none are found,
so it can never succeed on an empty set.
"""
import glob
import json
import os

import pytest

from agent.machine import AgentMachine
from agent.replies import PROMPTS, reply_for
from config import CLINIC_FILE

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


def all_conversations():
    out = []
    for folder in ("conversations", "adversarial"):
        for path in sorted(glob.glob(os.path.join(ROOT, folder, "*.json"))):
            with open(path, encoding="utf-8") as f:
                out.append(json.load(f))
    return out


def replay(conv):
    """Replay the way the API does: a reply after each non-final turn, silence after a handoff, then finalize."""
    m = AgentMachine(CLINIC_FILE, ":memory:", conv["today"])
    shown = []   # (turn index, reply text) as the transcript would show them
    turns = conv["turns"]
    for i, turn in enumerate(turns):
        m.is_last_turn = i == len(turns) - 1
        handed_off_before = m.terminal_state in ("escalated", "refused")
        m.process_turn(turn)
        if not m.is_last_turn and not handed_off_before:
            shown.append((i, reply_for(m), m))
    res = m.finalize()
    if not shown or res["reply"] != shown[-1][1]:
        shown.append((len(turns) - 1, res["reply"], m))
    m.conn.close()
    return shown, res


def test_conversations_are_found():
    assert len(all_conversations()) >= 19


@pytest.mark.parametrize("conv", all_conversations(), ids=lambda c: c["id"])
def test_no_two_consecutive_agent_replies_are_identical(conv):
    shown, _ = replay(conv)
    texts = [t for _, t, _ in shown]
    for a, b in zip(texts, texts[1:]):
        assert a != b, f"{conv['id']}: repeated reply: {a}"


@pytest.mark.parametrize("conv", all_conversations(), ids=lambda c: c["id"])
def test_no_filler_replies(conv):
    shown, _ = replay(conv)
    banned = [PROMPTS_text for key in ("hi", "en") for PROMPTS_text in ["Dhanyavaad, note kar liya.", "Thank you, noted."]]
    for _, text, _ in shown:
        assert text not in banned, f"{conv['id']}: filler reply: {text}"


@pytest.mark.parametrize("conv", all_conversations(), ids=lambda c: c["id"])
def test_replies_do_not_contradict_the_tool_result(conv):
    """A reply about candidates or a missing record must match the lookup that just ran."""
    m = AgentMachine(CLINIC_FILE, ":memory:", conv["today"])
    turns = conv["turns"]
    for i, turn in enumerate(turns):
        m.is_last_turn = i == len(turns) - 1
        calls_before = len(m.tool_calls)
        handed_off_before = m.terminal_state in ("escalated", "refused")
        m.process_turn(turn)
        if m.is_last_turn or handed_off_before:
            continue
        reply = reply_for(m)
        for call in m.tool_calls[calls_before:]:
            if call["name"] != "lookup_patient" or not call.get("result"):
                continue
            status = call["result"].get("status")
            said_several = any(PROMPTS["ask_more_identity"][lang] in reply for lang in ("en", "hi"))
            said_not_found = any(PROMPTS["ask_no_match"][lang] in reply for lang in ("en", "hi"))
            if status == "candidates":
                assert not said_not_found, f"{conv['id']}: said 'not found' but the lookup returned candidates"
            if status == "none":
                assert not said_several, f"{conv['id']}: said 'several records' but the lookup found none"
            if status == "match":
                assert not said_several and not said_not_found, f"{conv['id']}: reply contradicts a match"
    m.conn.close()


def _summary_of(conv):
    m = AgentMachine(CLINIC_FILE, ":memory:", conv["today"])
    for i, t in enumerate(conv["turns"]):
        m.is_last_turn = i == len(conv["turns"]) - 1
        m.process_turn(t)
    m.finalize()
    m.conn.close()
    call = next(c for c in m.tool_calls if c["name"] == "escalate_to_human")
    return call["arguments"]["summary"]


def test_escalation_summary_uses_the_date_and_time_the_caller_gave():
    # Not the cv_0011 script: Dr. Sethi, a Wednesday, a different time.
    conv = {"id": "sum_1", "today": "2026-10-01", "turns": [
        "Dr. Sethi ke saath Budhwar 3 baje appointment chahiye.",
        "Mujhe seene mein dard ho raha hai.",
    ]}
    summary = _summary_of(conv)
    assert "kal" not in summary and "10:00" not in summary, summary
    assert "Sethi" in summary, summary
    assert "Wed 7 Oct" in summary and "15:00" in summary, summary


def test_escalation_summary_has_no_date_when_none_was_given():
    conv = {"id": "sum_2", "today": "2026-10-01", "turns": [
        "Dr. Rao ke saath appointment chahiye.",
        "Mujhe seene mein dard ho raha hai.",
    ]}
    summary = _summary_of(conv)
    assert "(" not in summary, summary


def test_intent_is_stored_for_the_ui_but_not_in_the_graded_response():
    """The UI banner reads the intent. It must be saved, and must not leak into /agent/run."""
    from fastapi.testclient import TestClient
    from app.main import app
    client = TestClient(app)
    expected = {"cv_0007": "book", "cv_0009": "cancel", "cv_0010": None, "cv_0011": "book"}
    for cid, intent in expected.items():
        conv = next(c for c in all_conversations() if c["id"] == cid)
        body = client.post("/agent/run", json={"conversation_id": cid, "today": conv["today"], "turns": conv["turns"]}).json()
        assert "intent" not in body, cid
        assert client.get(f"/conversations/{cid}").json()["intent"] == intent, cid


def test_ticket_ids_restart_for_every_run():
    from tools.agent_tools import escalate_to_human
    from tools.store import load_run_store
    for _ in range(2):
        conn = load_run_store(CLINIC_FILE, ":memory:")
        assert escalate_to_human(conn, "out_of_scope", "test")["ticket_id"] == 1
        conn.close()


def test_cv_0007_second_turn_moves_towards_a_handoff():
    conv = next(c for c in all_conversations() if c["id"] == "cv_0007")
    shown, res = replay(conv)
    texts = [t for _, t, _ in shown]
    assert texts[0] == PROMPTS["ask_more_identity"]["hi"]
    assert "connect" in texts[1], texts[1]
    assert res["escalation_reason"] == "ambiguous_patient"


def test_cv_0011_does_not_ask_for_the_patient_twice_in_a_row():
    conv = next(c for c in all_conversations() if c["id"] == "cv_0011")
    shown, _ = replay(conv)
    texts = [t for _, t, _ in shown]
    assert texts[0] != texts[1]


def test_after_a_handoff_the_agent_speaks_once():
    conv = next(c for c in all_conversations() if c["id"] == "cv_0010")
    shown, _ = replay(conv)
    texts = [t for _, t, _ in shown]
    handoff = [t for t in texts if "salah nahi de sakti" in t]
    assert len(handoff) == 1
