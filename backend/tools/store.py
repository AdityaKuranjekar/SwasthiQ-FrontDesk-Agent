import sqlite3
import json
from dataclasses import dataclass
from typing import Optional, List, Dict, Any

def init_db(db_path: str):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    
    c.executescript("""
    CREATE TABLE IF NOT EXISTS patients (
        id TEXT PRIMARY KEY,
        name TEXT,
        phone TEXT,
        dob TEXT,
        guardian_of_json TEXT
    );
    
    CREATE TABLE IF NOT EXISTS doctors (
        id TEXT PRIMARY KEY,
        name TEXT,
        speciality TEXT
    );
    
    CREATE TABLE IF NOT EXISTS appointments (
        id TEXT PRIMARY KEY,
        patient_id TEXT,
        doctor_id TEXT,
        date TEXT,
        start TEXT,
        end TEXT,
        status TEXT
    );
    
    CREATE TABLE IF NOT EXISTS handoffs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        reason TEXT,
        summary TEXT,
        patient_id TEXT,
        appointment_id TEXT
    );
    
    CREATE UNIQUE INDEX IF NOT EXISTS idx_booked_slot 
    ON appointments (doctor_id, date, start) 
    WHERE status = 'booked';
    """)
    
    conn.commit()
    return conn

def load_run_store(clinic_path: str, db_path: str) -> sqlite3.Connection:
    conn = init_db(db_path)
    c = conn.cursor()
    
    # Clear existing data for fresh run
    c.executescript("""
        DELETE FROM patients;
        DELETE FROM doctors;
        DELETE FROM appointments;
        DELETE FROM handoffs;
    """)
    
    with open(clinic_path, "r", encoding="utf-8") as f:
        data = json.load(f)
        
    for p in data.get("patients", []):
        c.execute("INSERT INTO patients (id, name, phone, dob, guardian_of_json) VALUES (?, ?, ?, ?, ?)",
                  (p["id"], p["name"], p["phone"], p["dob"], json.dumps(p.get("guardian_of", []))))
                  
    for d in data.get("doctors", []):
        c.execute("INSERT INTO doctors (id, name, speciality) VALUES (?, ?, ?)",
                  (d["id"], d["name"], d["speciality"]))
                  
    for a in data.get("appointments", []):
        c.execute("INSERT INTO appointments (id, patient_id, doctor_id, date, start, end, status) VALUES (?, ?, ?, ?, ?, ?, ?)",
                  (a["id"], a["patient_id"], a["doctor_id"], a["date"], a["start"], a["end"], a["status"]))
                  
    conn.commit()
    return conn
