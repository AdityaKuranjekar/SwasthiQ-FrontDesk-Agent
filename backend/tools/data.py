import json
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Set, Tuple
from datetime import datetime, timedelta

@dataclass(frozen=True)
class ClinicWindow:
    day: str
    start: str
    end: str

@dataclass(frozen=True)
class Doctor:
    id: str
    name: str
    speciality: str
    windows: List[ClinicWindow]
    leave_dates: List[str]

@dataclass(frozen=True)
class Patient:
    id: str
    name: str
    phone: str
    dob: str
    guardian_of: List[str]

@dataclass(frozen=True)
class Appointment:
    id: str
    patient_id: str
    doctor_id: str
    date: str
    start: str
    end: str
    status: str

@dataclass(frozen=True)
class ClinicData:
    clinic: dict
    doctors: Dict[str, Doctor]
    holidays: List[str]
    patients: Dict[str, Patient]
    appointments: List[Appointment]

def load_clinic_data(path: str) -> ClinicData:
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    doctors = {}
    for d in data["doctors"]:
        windows = [ClinicWindow(**w) for w in d["windows"]]
        doctors[d["id"]] = Doctor(
            id=d["id"], name=d["name"], speciality=d["speciality"],
            windows=windows, leave_dates=d.get("leave_dates", [])
        )
    
    patients = {}
    for p in data["patients"]:
        patients[p["id"]] = Patient(**p)
    
    appointments = [Appointment(**a) for a in data["appointments"]]
    
    return ClinicData(
        clinic=data["clinic"],
        doctors=doctors,
        holidays=data.get("holidays", []),
        patients=patients,
        appointments=appointments
    )

def _time_to_mins(t: str) -> int:
    h, m = map(int, t.split(":"))
    return h * 60 + m

def _mins_to_time(m: int) -> str:
    return f"{m // 60:02d}:{m % 60:02d}"

def merge_windows(windows: List[ClinicWindow]) -> List[Tuple[int, int]]:
    if not windows:
        return []
    intervals = sorted([(_time_to_mins(w.start), _time_to_mins(w.end)) for w in windows])
    merged = [intervals[0]]
    for current in intervals[1:]:
        last = merged[-1]
        if current[0] <= last[1]:
            merged[-1] = (last[0], max(last[1], current[1]))
        else:
            merged.append(current)
    return merged

def get_slots(clinic_data: ClinicData, doctor_id: str, date_str: str) -> List[str]:
    # Check if Sunday
    dt = datetime.strptime(date_str, "%Y-%m-%d")
    if dt.strftime("%a") == "Sun":
        return []
    
    # Check holiday
    if date_str in clinic_data.holidays:
        return []
        
    doctor = clinic_data.doctors.get(doctor_id)
    if not doctor:
        return []
        
    # Check leave
    if date_str in doctor.leave_dates:
        return []
        
    # Get matching day windows
    day_short = dt.strftime("%a")
    day_windows = [w for w in doctor.windows if w.day == day_short]
    merged = merge_windows(day_windows)
    
    # Generate 15-min slots
    slots = []
    for start_m, end_m in merged:
        curr = start_m
        while curr + 15 <= end_m:
            slots.append(_mins_to_time(curr))
            curr += 15
            
    # Remove occupied
    occupied = {a.start for a in clinic_data.appointments if a.doctor_id == doctor_id and a.date == date_str and a.status == "booked"}
    available = [s for s in slots if s not in occupied]
    
    return sorted(available)
