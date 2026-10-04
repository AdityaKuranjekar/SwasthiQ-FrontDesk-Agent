import os
import pytest
import sqlite3
from tools.store import load_run_store, init_db
from config import CLINIC_FILE

@pytest.fixture
def fresh_store():
    # use in-memory db for tests
    conn = load_run_store(CLINIC_FILE, ":memory:")
    yield conn
    conn.close()

def test_unique_index_blocks_duplicate_booked(fresh_store):
    c = fresh_store.cursor()
    c.execute("""
        INSERT INTO appointments (id, patient_id, doctor_id, date, start, end, status)
        VALUES ('test_ap_1', 'pt_0001', 'dr_rao', '2026-10-02', '10:00', '10:15', 'booked')
    """)
    fresh_store.commit()
    
    with pytest.raises(sqlite3.IntegrityError):
        c.execute("""
            INSERT INTO appointments (id, patient_id, doctor_id, date, start, end, status)
            VALUES ('test_ap_2', 'pt_0002', 'dr_rao', '2026-10-02', '10:00', '10:15', 'booked')
        """)
        fresh_store.commit()

def test_cancelled_slot_reusable(fresh_store):
    c = fresh_store.cursor()
    c.execute("""
        INSERT INTO appointments (id, patient_id, doctor_id, date, start, end, status)
        VALUES ('test_ap_1', 'pt_0001', 'dr_rao', '2026-10-02', '10:00', '10:15', 'cancelled')
    """)
    fresh_store.commit()
    
    # Should not raise exception
    c.execute("""
        INSERT INTO appointments (id, patient_id, doctor_id, date, start, end, status)
        VALUES ('test_ap_2', 'pt_0002', 'dr_rao', '2026-10-02', '10:00', '10:15', 'booked')
    """)
    fresh_store.commit()

def test_fresh_store_per_run():
    # Use a file DB to test clearing
    db_path = "test_run.db"
    if os.path.exists(db_path):
        os.remove(db_path)
        
    conn1 = load_run_store(CLINIC_FILE, db_path)
    c1 = conn1.cursor()
    c1.execute("""
        INSERT INTO appointments (id, patient_id, doctor_id, date, start, end, status)
        VALUES ('test_ap_999', 'pt_0001', 'dr_rao', '2099-10-02', '10:00', '10:15', 'booked')
    """)
    conn1.commit()
    conn1.close()
    
    conn2 = load_run_store(CLINIC_FILE, db_path)
    c2 = conn2.cursor()
    c2.execute("SELECT count(*) FROM appointments WHERE id='test_ap_999'")
    assert c2.fetchone()[0] == 0
    conn2.close()
    
    if os.path.exists(db_path):
        os.remove(db_path)
