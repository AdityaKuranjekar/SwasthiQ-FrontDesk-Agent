import re
import uuid
import json
from datetime import datetime
from typing import Dict, Any, Optional

def _error(code: str, field: Optional[str] = None, message: str = "", expected: Any = None) -> Dict[str, Any]:
    err = {"code": code, "message": message}
    if field is not None:
        err["field"] = field
    if expected is not None:
        err["expected"] = expected
    return {"ok": False, "error": err}

def search_slots(conn, clinic_data, doctor_id: str, date: str) -> Dict[str, Any]:
    # Check date format
    try:
        datetime.strptime(date, "%Y-%m-%d")
    except ValueError:
        return _error("invalid_date", "date")
        
    doctor = clinic_data.doctors.get(doctor_id)
    if not doctor:
        return _error("unknown_doctor", "doctor_id")
        
    # Get base slots from data.py logic
    # We will replicate the slot logic but exclude DB booked slots
    from tools.data import get_slots
    
    # get_slots currently checks clinic_data.appointments. We need to override it or manually do it.
    # Actually, let's let get_slots do its thing for holidays/leave, but we filter based on DB.
    # To do this cleanly, we can fetch all slots without considering appointments (temporarily patch or recreate logic)
    # Let's just recreate it quickly to be safe and accurate with DB:
    dt = datetime.strptime(date, "%Y-%m-%d")
    if dt.strftime("%a") == "Sun" or date in clinic_data.holidays or date in doctor.leave_dates:
        return {"ok": True, "slots": []}
        
    from tools.data import merge_windows, _mins_to_time
    day_short = dt.strftime("%a")
    day_windows = [w for w in doctor.windows if w.day == day_short]
    merged = merge_windows(day_windows)
    
    slots = []
    for start_m, end_m in merged:
        curr = start_m
        while curr + 15 <= end_m:
            slots.append(_mins_to_time(curr))
            curr += 15
            
    c = conn.cursor()
    c.execute("SELECT start FROM appointments WHERE doctor_id = ? AND date = ? AND status = 'booked'", (doctor_id, date))
    occupied = {row[0] for row in c.fetchall()}
    
    available = sorted([s for s in slots if s not in occupied])
    return {"ok": True, "slots": available}

def lookup_patient(conn, name: Optional[str] = None, phone: Optional[str] = None, dob: Optional[str] = None) -> Dict[str, Any]:
    c = conn.cursor()
    
    query = "SELECT id, name, phone, dob FROM patients WHERE 1=1"
    params = []
    
    if name:
        # Normalize name: lower, remove dots, extra spaces
        n_name = re.sub(r'[^a-z0-9]', '', name.lower())
    else:
        n_name = None
        
    if phone:
        n_phone = re.sub(r'\D', '', phone)
    else:
        n_phone = None
        
    c.execute(query)
    rows = c.fetchall()
    
    matches = []
    for r in rows:
        match = True
        if n_name:
            r_name = re.sub(r'[^a-z0-9]', '', r["name"].lower())
            # For this simple mock, we do substring or exact? 
            # Prompt says "lookup_patient on ambiguous name must return candidates... surname 'Sharma' returns candidates"
            if n_name not in r_name:
                match = False
        if n_phone and n_phone != r["phone"]:
            match = False
        if dob and dob != r["dob"]:
            match = False
            
        if match:
            matches.append({"id": r["id"], "name": r["name"], "phone": r["phone"], "dob": r["dob"]})
            
    if not matches:
        return {"ok": True, "status": "none"}
    elif len(matches) == 1:
        return {"ok": True, "status": "match", "patient": matches[0]}
    else:
        return {"ok": True, "status": "candidates", "patients": matches}

def _check_authority(conn, actor_patient_id: str, target_patient_id: str) -> bool:
    if actor_patient_id == target_patient_id:
        return True
    c = conn.cursor()
    c.execute("SELECT guardian_of_json FROM patients WHERE id = ?", (actor_patient_id,))
    row = c.fetchone()
    if not row:
        return False
    guardians = json.loads(row["guardian_of_json"])
    return target_patient_id in guardians

def book_appointment(conn, clinic_data, actor_patient_id: str, patient_id: str, doctor_id: str, date: str, start: str) -> Dict[str, Any]:
    # 1. Malformed input
    try:
        datetime.strptime(date, "%Y-%m-%d")
    except ValueError:
        return _error("invalid_date", "date")
        
    if start[-3:] not in [":00", ":15", ":30", ":45"]:
        return _error("not_on_slot_grid", "start")
        
    doctor = clinic_data.doctors.get(doctor_id)
    if not doctor:
        return _error("unknown_doctor", "doctor_id")
        
    slot_error = _target_slot_error(clinic_data, doctor_id, date, start)
    if slot_error:
        return slot_error

    # 2. Existence
    c = conn.cursor()
    c.execute("SELECT id FROM appointments WHERE doctor_id = ? AND date = ? AND start = ? AND status = 'booked'", (doctor_id, date, start))
    if c.fetchone():
        return _error("slot_unavailable", "start")
        
    # 3. Authority
    if not _check_authority(conn, actor_patient_id, patient_id):
        return _error("unauthorised_actor", "actor_patient_id")
        
    ap_id = "ap_" + uuid.uuid4().hex[:8]
    # start + 15 mins
    h, m = map(int, start.split(":"))
    end_m = h * 60 + m + 15
    end = f"{end_m // 60:02d}:{end_m % 60:02d}"
    
    try:
        c.execute("INSERT INTO appointments (id, patient_id, doctor_id, date, start, end, status) VALUES (?, ?, ?, ?, ?, ?, 'booked')",
                  (ap_id, patient_id, doctor_id, date, start, end))
        conn.commit()
    except Exception:
        return _error("slot_unavailable", "start")
        
    return {"ok": True, "appointment_id": ap_id}

def _target_slot_error(clinic_data, doctor_id: str, date: str, start: str) -> Optional[Dict[str, Any]]:
    """Return an error if the slot is not a real bookable slot for this doctor, else None."""
    from tools.data import merge_windows, _mins_to_time
    doctor = clinic_data.doctors[doctor_id]
    dt = datetime.strptime(date, "%Y-%m-%d")
    if dt.strftime("%a") == "Sun" or date in clinic_data.holidays:
        return _error("clinic_closed", "date")
    if date in doctor.leave_dates:
        return _error("doctor_on_leave", "date")
    day_short = dt.strftime("%a")
    merged = merge_windows([w for w in doctor.windows if w.day == day_short])
    valid = set()
    for start_m, end_m in merged:
        curr = start_m
        while curr + 15 <= end_m:
            valid.add(_mins_to_time(curr))
            curr += 15
    if start not in valid:
        return _error("outside_window", "start")
    return None

def reschedule_appointment(conn, clinic_data, actor_patient_id: str, appointment_id: str, date: str, start: str, doctor_id: Optional[str] = None) -> Dict[str, Any]:
    try:
        datetime.strptime(date, "%Y-%m-%d")
    except ValueError:
        return _error("invalid_date", "date")
        
    if start[-3:] not in [":00", ":15", ":30", ":45"]:
        return _error("not_on_slot_grid", "start")
        
    c = conn.cursor()
    c.execute("SELECT * FROM appointments WHERE id = ?", (appointment_id,))
    row = c.fetchone()
    
    if not row:
        return _error("unknown_appointment", "appointment_id")
        
    if row["status"] != "booked":
        return _error("already_cancelled", "appointment_id")
        
    tgt_doctor = doctor_id if doctor_id else row["doctor_id"]
    if tgt_doctor not in clinic_data.doctors:
        return _error("unknown_doctor", "doctor_id")
        
    # Same slot check
    if row["date"] == date and row["start"] == start and row["doctor_id"] == tgt_doctor:
        return _error("same_slot", "start")
        
    # Authority
    if not _check_authority(conn, actor_patient_id, row["patient_id"]):
        return _error("unauthorised_actor", "actor_patient_id")
        
    # The target must be a real slot for that doctor: open day, not on leave, inside a window
    slot_error = _target_slot_error(clinic_data, tgt_doctor, date, start)
    if slot_error:
        return slot_error

    # Existence (Availability)
    c.execute("SELECT id FROM appointments WHERE doctor_id = ? AND date = ? AND start = ? AND status = 'booked'", (tgt_doctor, date, start))
    if c.fetchone():
        return _error("slot_unavailable", "start")
        
    h, m = map(int, start.split(":"))
    end = f"{h + (m+15)//60:02d}:{(m+15)%60:02d}"
    
    c.execute("UPDATE appointments SET date = ?, start = ?, end = ?, doctor_id = ? WHERE id = ?",
              (date, start, end, tgt_doctor, appointment_id))
    conn.commit()
    
    return {"ok": True, "appointment_id": appointment_id}

def cancel_appointment(conn, actor_patient_id: str, appointment_id: str) -> Dict[str, Any]:
    c = conn.cursor()
    c.execute("SELECT patient_id, status FROM appointments WHERE id = ?", (appointment_id,))
    row = c.fetchone()
    if not row:
        return _error("unknown_appointment", "appointment_id")
        
    if row["status"] == "cancelled":
        return _error("already_cancelled", "appointment_id")
        
    if not _check_authority(conn, actor_patient_id, row["patient_id"]):
        return _error("unauthorised_actor", "actor_patient_id")
        
    c.execute("UPDATE appointments SET status = 'cancelled' WHERE id = ?", (appointment_id,))
    conn.commit()
    
    return {"ok": True, "appointment_id": appointment_id}

def escalate_to_human(conn, reason: str, summary: str, patient_id: Optional[str] = None, appointment_id: Optional[str] = None) -> Dict[str, Any]:
    valid_reasons = {"clinical_urgent", "medical_advice", "not_authorised", "ambiguous_patient", "out_of_scope"}
    if reason not in valid_reasons:
        return _error("invalid_reason", "reason")
        
    c = conn.cursor()
    c.execute("INSERT INTO handoffs (reason, summary, patient_id, appointment_id) VALUES (?, ?, ?, ?)",
              (reason, summary, patient_id, appointment_id))
    ticket_id = c.lastrowid
    conn.commit()
    
    return {"ok": True, "ticket_id": ticket_id}
