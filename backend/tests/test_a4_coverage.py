"""Coverage tests for the tool layer.

Covers the paths the Phase A tests did not reach: reschedule and cancel success
and error branches, escalation success, and input-validation branches.

Tests marked xfail(strict=True) pin behaviour the contract requires but the
current code does not yet provide. They are tracked defects, not passing
features. When a defect is fixed, its xfail test starts passing, strict mode
fails the run, and the marker must be removed.
"""
import pytest

from tools.store import load_run_store
from tools.data import load_clinic_data
from config import CLINIC_FILE
from tools.agent_tools import (
    search_slots, lookup_patient, book_appointment,
    reschedule_appointment, cancel_appointment, escalate_to_human,
)


@pytest.fixture
def store():
    conn = load_run_store(CLINIC_FILE, ":memory:")
    yield conn
    conn.close()


@pytest.fixture
def clinic_data():
    return load_clinic_data(CLINIC_FILE)


# --- search_slots -----------------------------------------------------------

def test_search_invalid_date(store, clinic_data):
    res = search_slots(store, clinic_data, "dr_rao", "2026-13-40")
    assert res["error"]["code"] == "invalid_date"
    assert res["error"]["field"] == "date"


def test_search_unknown_doctor(store, clinic_data):
    res = search_slots(store, clinic_data, "dr_nobody", "2026-10-03")
    assert res["error"]["code"] == "unknown_doctor"


def test_search_sunday_is_empty(store, clinic_data):
    res = search_slots(store, clinic_data, "dr_rao", "2026-10-04")
    assert res == {"ok": True, "slots": [], "closed_reason": "clinic_closed"}


# --- lookup_patient ---------------------------------------------------------

def test_lookup_dob_filters_candidates(store):
    res = lookup_patient(store, phone="9812200166", dob="2014-04-18")
    assert res["status"] == "candidates"
    assert {p["id"] for p in res["patients"]} == {"pt_0006", "pt_0007"}


def test_lookup_unknown_name_is_none(store):
    res = lookup_patient(store, name="Zorro Nobody")
    assert res == {"ok": True, "status": "none"}


def test_lookup_without_identifiers_is_rejected(store):
    res = lookup_patient(store)
    assert res["ok"] is False
    assert res["error"]["code"] == "no_identifier"


# --- book_appointment -------------------------------------------------------

def test_book_invalid_date(store, clinic_data):
    res = book_appointment(store, clinic_data, "pt_0013", "pt_0013", "dr_rao", "2026-02-30", "11:00")
    assert res["error"]["code"] == "invalid_date"


def test_book_unknown_doctor(store, clinic_data):
    res = book_appointment(store, clinic_data, "pt_0013", "pt_0013", "dr_nobody", "2026-10-03", "11:00")
    assert res["error"]["code"] == "unknown_doctor"


def test_book_unauthorised_actor(store, clinic_data):
    # pt_0020 (Mohit) is not a guardian of pt_0012 (Lakshmi).
    res = book_appointment(store, clinic_data, "pt_0020", "pt_0012", "dr_rao", "2026-10-03", "11:00")
    assert res["error"]["code"] == "unauthorised_actor"


def test_book_unknown_actor_is_unauthorised(store, clinic_data):
    res = book_appointment(store, clinic_data, "pt_9999", "pt_0013", "dr_rao", "2026-10-03", "11:00")
    assert res["error"]["code"] == "unknown_patient"


def test_book_on_holiday_reports_clinic_closed(store, clinic_data):
    res = book_appointment(store, clinic_data, "pt_0013", "pt_0013", "dr_rao", "2026-10-02", "11:00")
    assert res["error"]["code"] == "clinic_closed"


def test_book_on_leave_reports_doctor_on_leave(store, clinic_data):
    res = book_appointment(store, clinic_data, "pt_0013", "pt_0013", "dr_sethi", "2026-10-05", "10:00")
    assert res["error"]["code"] == "doctor_on_leave"


# --- reschedule_appointment -------------------------------------------------

def test_reschedule_success(store, clinic_data):
    # ap_0001 belongs to pt_0001 and sits on 2026-10-01 09:30.
    res = reschedule_appointment(store, clinic_data, "pt_0001", "ap_0001", "2026-10-03", "10:00")
    assert res == {"ok": True, "appointment_id": "ap_0001"}
    row = store.execute("SELECT date, start, end FROM appointments WHERE id = 'ap_0001'").fetchone()
    assert (row["date"], row["start"], row["end"]) == ("2026-10-03", "10:00", "10:15")


def test_reschedule_invalid_date(store, clinic_data):
    res = reschedule_appointment(store, clinic_data, "pt_0001", "ap_0001", "not-a-date", "10:00")
    assert res["error"]["code"] == "invalid_date"


def test_reschedule_off_grid(store, clinic_data):
    res = reschedule_appointment(store, clinic_data, "pt_0001", "ap_0001", "2026-10-03", "10:20")
    assert res["error"]["code"] == "not_on_slot_grid"


def test_reschedule_unknown_appointment(store, clinic_data):
    res = reschedule_appointment(store, clinic_data, "pt_0001", "ap_9999", "2026-10-03", "10:00")
    assert res["error"]["code"] == "unknown_appointment"


def test_reschedule_cancelled_appointment(store, clinic_data):
    cancel_appointment(store, "pt_0001", "ap_0001")
    res = reschedule_appointment(store, clinic_data, "pt_0001", "ap_0001", "2026-10-03", "10:00")
    assert res["error"]["code"] == "already_cancelled"


def test_reschedule_unknown_doctor(store, clinic_data):
    res = reschedule_appointment(store, clinic_data, "pt_0001", "ap_0001", "2026-10-03", "10:00", doctor_id="dr_nobody")
    assert res["error"]["code"] == "unknown_doctor"


def test_reschedule_unauthorised_actor(store, clinic_data):
    res = reschedule_appointment(store, clinic_data, "pt_0020", "ap_0001", "2026-10-03", "10:00")
    assert res["error"]["code"] == "unauthorised_actor"


def test_reschedule_into_taken_slot(store, clinic_data):
    # ap_0006 holds Dr. Rao, 2026-10-03 09:15.
    res = reschedule_appointment(store, clinic_data, "pt_0001", "ap_0001", "2026-10-03", "09:15")
    assert res["error"]["code"] == "slot_unavailable"


def test_reschedule_to_sunday_is_rejected(store, clinic_data):
    res = reschedule_appointment(store, clinic_data, "pt_0001", "ap_0001", "2026-10-04", "10:00")
    assert res["ok"] is False
    assert res["error"]["code"] == "clinic_closed"


def test_reschedule_to_holiday_is_rejected(store, clinic_data):
    res = reschedule_appointment(store, clinic_data, "pt_0001", "ap_0001", "2026-10-02", "10:00")
    assert res["error"]["code"] == "clinic_closed"


def test_reschedule_to_leave_day_is_rejected(store, clinic_data):
    # Dr. Sethi is on leave 2026-10-05 to 07.
    res = reschedule_appointment(store, clinic_data, "pt_0031", "ap_0004", "2026-10-05", "10:00", doctor_id="dr_sethi")
    assert res["error"]["code"] == "doctor_on_leave"


def test_reschedule_outside_window_is_rejected(store, clinic_data):
    # Dr. Rao's Saturday window ends at 13:00.
    res = reschedule_appointment(store, clinic_data, "pt_0001", "ap_0001", "2026-10-03", "13:30")
    assert res["error"]["code"] == "outside_window"


def test_rejected_reschedule_leaves_appointment_unchanged(store, clinic_data):
    reschedule_appointment(store, clinic_data, "pt_0001", "ap_0001", "2026-10-04", "10:00")
    row = store.execute("SELECT date, start FROM appointments WHERE id = 'ap_0001'").fetchone()
    assert (row["date"], row["start"]) == ("2026-10-01", "09:30")


# --- cancel_appointment -----------------------------------------------------

def test_cancel_success_then_already_cancelled(store):
    res = cancel_appointment(store, "pt_0004", "ap_0002")
    assert res == {"ok": True, "appointment_id": "ap_0002"}
    status = store.execute("SELECT status FROM appointments WHERE id = 'ap_0002'").fetchone()["status"]
    assert status == "cancelled"
    again = cancel_appointment(store, "pt_0004", "ap_0002")
    assert again["error"]["code"] == "already_cancelled"


def test_cancel_unknown_appointment(store):
    res = cancel_appointment(store, "pt_0004", "ap_9999")
    assert res["error"]["code"] == "unknown_appointment"


def test_cancel_unauthorised_actor(store):
    res = cancel_appointment(store, "pt_0020", "ap_0002")
    assert res["error"]["code"] == "unauthorised_actor"


# --- escalate_to_human ------------------------------------------------------

def test_escalate_success_writes_handoff(store):
    res = escalate_to_human(store, "clinical_urgent", "chest pain reported", patient_id="pt_0013")
    assert res["ok"] is True
    assert isinstance(res["ticket_id"], int)
    row = store.execute("SELECT reason, summary, patient_id FROM handoffs WHERE id = ?", (res["ticket_id"],)).fetchone()
    assert (row["reason"], row["summary"], row["patient_id"]) == ("clinical_urgent", "chest pain reported", "pt_0013")
