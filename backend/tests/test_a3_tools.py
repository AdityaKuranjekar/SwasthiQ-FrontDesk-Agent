import pytest
import sqlite3
import threading
from tools.store import load_run_store
from tools.data import load_clinic_data
from config import CLINIC_FILE
from tools.agent_tools import (
    search_slots, lookup_patient, book_appointment,
    reschedule_appointment, cancel_appointment, escalate_to_human
)

@pytest.fixture
def store():
    conn = load_run_store(CLINIC_FILE, ":memory:")
    yield conn
    conn.close()
    
@pytest.fixture
def clinic_data():
    return load_clinic_data(CLINIC_FILE)

def test_search_happy(store, clinic_data):
    res = search_slots(store, clinic_data, "dr_rao", "2026-10-03")
    assert res["ok"]
    # ap_0006 at 09:15 and ap_0007 at 09:45 are booked. 
    # Saturday window is 09:00 to 13:00.
    assert "09:00" in res["slots"]
    assert "09:15" not in res["slots"]
    assert "09:45" not in res["slots"]

def test_lookup_phone_and_name_match(store):
    res = lookup_patient(store, name="Rajesh Kumar Sharma", phone="9812200011")
    assert res["ok"]
    assert res["status"] == "match"
    assert res["patient"]["id"] == "pt_0001"

def test_lookup_shared_phone_candidates(store):
    res = lookup_patient(store, phone="9812200166")
    assert res["ok"]
    assert res["status"] == "candidates"
    assert len(res["patients"]) == 3

def test_lookup_surname_candidates(store):
    res = lookup_patient(store, name="Sharma")
    assert res["ok"]
    assert res["status"] == "candidates"
    assert len(res["patients"]) >= 2

def test_book_happy(store, clinic_data):
    res = book_appointment(store, clinic_data, "pt_0013", "pt_0013", "dr_rao", "2026-10-03", "11:00")
    assert res["ok"]
    assert "appointment_id" in res

def test_book_double_sequential(store, clinic_data):
    res1 = book_appointment(store, clinic_data, "pt_0013", "pt_0013", "dr_rao", "2026-10-03", "11:15")
    assert res1["ok"]
    res2 = book_appointment(store, clinic_data, "pt_0014", "pt_0014", "dr_rao", "2026-10-03", "11:15")
    assert not res2["ok"]
    assert res2["error"]["code"] == "slot_unavailable"

def test_book_double_threaded(clinic_data, tmp_path):
    db_file = str(tmp_path / "test_db.sqlite")
    conn = sqlite3.connect(db_file)
    import json
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.executescript("""
        CREATE TABLE IF NOT EXISTS patients (id TEXT PRIMARY KEY, name TEXT, phone TEXT, dob TEXT, guardian_of_json TEXT);
        CREATE TABLE IF NOT EXISTS doctors (id TEXT PRIMARY KEY, name TEXT, speciality TEXT);
        CREATE TABLE IF NOT EXISTS appointments (id TEXT PRIMARY KEY, patient_id TEXT, doctor_id TEXT, date TEXT, start TEXT, end TEXT, status TEXT);
        CREATE UNIQUE INDEX IF NOT EXISTS idx_booked_slot ON appointments (doctor_id, date, start) WHERE status = 'booked';
    """)
    with open(CLINIC_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    for p in data.get("patients", []):
        c.execute("INSERT INTO patients (id, name, phone, dob, guardian_of_json) VALUES (?, ?, ?, ?, ?)", (p["id"], p["name"], p["phone"], p["dob"], json.dumps(p.get("guardian_of", []))))
    for d in data.get("doctors", []):
        c.execute("INSERT INTO doctors (id, name, speciality) VALUES (?, ?, ?)", (d["id"], d["name"], d["speciality"]))
    conn.commit()
    conn.close()

    results = []
    import threading
    barrier = threading.Barrier(20)
    
    def worker():
        try:
            worker_conn = sqlite3.connect(db_file, timeout=20.0)
            worker_conn.row_factory = sqlite3.Row
            barrier.wait()
            res = book_appointment(worker_conn, clinic_data, "pt_0013", "pt_0013", "dr_rao", "2026-10-03", "12:00")
            results.append(res)
        except Exception as e:
            results.append({"ok": False, "error": str(e)})
        finally:
            worker_conn.close()
            
    threads = [threading.Thread(target=worker) for _ in range(20)]
    for t in threads: t.start()
    for t in threads: t.join()
    
    successes = [r for r in results if r.get("ok")]
    assert len(successes) == 1
    
def test_guardian_authorised(store, clinic_data):
    res = book_appointment(store, clinic_data, "pt_0008", "pt_0006", "dr_rao", "2026-10-03", "11:30")
    assert res["ok"]

def test_unauthorised_actor(store):
    res = cancel_appointment(store, "pt_0020", "ap_0003")
    assert not res["ok"]
    assert res["error"]["code"] == "unauthorised_actor"

def test_reschedule_same_slot(store, clinic_data):
    # ap_0001 is pt_0001, dr_rao, 2026-10-01, 09:30
    res = reschedule_appointment(store, clinic_data, "pt_0001", "ap_0001", "2026-10-01", "09:30", "dr_rao")
    assert not res["ok"]
    assert res["error"]["code"] == "same_slot"

def test_cancel_twice(store):
    res1 = cancel_appointment(store, "pt_0001", "ap_0001")
    assert res1["ok"]
    res2 = cancel_appointment(store, "pt_0001", "ap_0001")
    assert not res2["ok"]
    assert res2["error"]["code"] == "already_cancelled"

def test_escalate_bad_reason(store):
    res = escalate_to_human(store, "angry_patient", "he is angry")
    assert not res["ok"]
    assert res["error"]["code"] == "invalid_reason"

def test_malformed_args(store, clinic_data):
    res1 = book_appointment(store, clinic_data, "pt_0001", "pt_0001", "dr_rao", "2026-13-45", "10:00")
    assert res1["error"]["code"] == "invalid_date"
    
    res2 = book_appointment(store, clinic_data, "pt_0001", "pt_0001", "dr_rao", "2026-10-03", "09:20")
    assert res2["error"]["code"] == "not_on_slot_grid"
    
    res3 = book_appointment(store, clinic_data, "pt_0001", "pt_0001", "dr_unknown", "2026-10-03", "10:00")
    assert res3["error"]["code"] == "unknown_doctor"

def test_error_order(store, clinic_data):
    # malformed input (bad date) vs existence (slot unavailable)
    # doctor exists but date is bad
    res1 = book_appointment(store, clinic_data, "pt_0001", "pt_0001", "dr_rao", "bad_date", "10:00")
    assert res1["error"]["code"] == "invalid_date"
    
    # existence vs authority
    # unauthorised actor trying to book an occupied slot
    # pt_0020 tries to book for pt_0001 on an occupied slot ap_0001 (dr_rao, 2026-10-01, 09:30)
    res2 = book_appointment(store, clinic_data, "pt_0020", "pt_0001", "dr_rao", "2026-10-01", "09:30")
    # should fail on existence (slot_unavailable) before authority check
    assert res2["error"]["code"] == "slot_unavailable"

def test_search_slots_closed_reasons(store, clinic_data):
    res = search_slots(store, clinic_data, "dr_rao", "2026-10-04") # Sunday
    assert res["ok"]
    assert res["closed_reason"] == "clinic_closed"

    res = search_slots(store, clinic_data, "dr_rao", "2026-10-02") # Holiday
    assert res["ok"]
    assert res["closed_reason"] == "clinic_closed"

    res = search_slots(store, clinic_data, "dr_sethi", "2026-10-01") # doctor_on_leave (Wait, let's verify if dr_sethi is on leave)
    res = search_slots(store, clinic_data, "dr_rao", "2026-10-09")
    assert res["ok"]
    assert res["closed_reason"] == "doctor_on_leave"

def test_malformed_lookup_patient(store):
    res = lookup_patient(store)
    assert res['ok'] is False
    assert res['error']['code'] == 'no_identifier'
    assert res['error']['field'] == 'name'

def test_malformed_search_slots(store, clinic_data):
    res = search_slots(store, clinic_data, 'dr_rao', 'bad-date')
    assert res['ok'] is False
    assert res['error']['code'] == 'invalid_date'
    assert res['error']['field'] == 'date'

def test_malformed_book_appointment(store, clinic_data):
    res = book_appointment(store, clinic_data, 'pt_0001', 'pt_xxx', 'dr_rao', '2026-10-03', '09:00')
    assert res['ok'] is False
    assert res['error']['code'] == 'unknown_patient'
    assert res['error']['field'] == 'patient_id'

def test_malformed_reschedule_appointment(store, clinic_data):
    res = reschedule_appointment(store, clinic_data, 'pt_0001', 'ap_0001', '2026-10-03', '09:12', 'dr_rao')
    assert res['ok'] is False
    assert res['error']['code'] == 'not_on_slot_grid'
    assert res['error']['field'] == 'start'
    
def test_malformed_reschedule_appointment_invalid_time(store, clinic_data):
    res = reschedule_appointment(store, clinic_data, 'pt_0001', 'ap_0001', '2026-10-03', 'xx:15', 'dr_rao')
    assert res['ok'] is False
    assert res['error']['code'] == 'invalid_time'
    assert res['error']['field'] == 'start'

def test_malformed_cancel_appointment(store):
    res = cancel_appointment(store, 'pt_xxx', 'ap_0001')
    assert res['ok'] is False
    assert res['error']['code'] == 'unknown_patient'
    assert res['error']['field'] == 'actor_patient_id'

def test_malformed_escalate_to_human(store):
    res = escalate_to_human(store, 'bad_reason', 'summary')
    assert res['ok'] is False
    assert res['error']['code'] == 'invalid_reason'
    assert res['error']['field'] == 'reason'
