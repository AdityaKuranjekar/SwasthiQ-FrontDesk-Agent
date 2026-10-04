import os
import pytest
from tools.data import load_clinic_data, get_slots, ClinicWindow, merge_windows
from config import CLINIC_FILE

@pytest.fixture
def clinic_data():
    return load_clinic_data(CLINIC_FILE)

def test_windows_merge():
    windows = [
        ClinicWindow("Mon", "09:00", "12:00"),
        ClinicWindow("Mon", "11:45", "15:00")
    ]
    merged = merge_windows(windows)
    assert merged == [(9*60, 15*60)]

def test_grid_15_min(clinic_data):
    # Dr. Rao Wed 09:00 - 12:00 and 16:00 - 19:00
    # 2026-10-07 is a Wednesday
    slots = get_slots(clinic_data, "dr_rao", "2026-10-07")
    for s in slots:
        assert s.endswith(":00") or s.endswith(":15") or s.endswith(":30") or s.endswith(":45")

def test_holiday_closed(clinic_data):
    # 2026-10-02 is a holiday
    slots = get_slots(clinic_data, "dr_rao", "2026-10-02")
    assert slots == []

def test_sunday_closed(clinic_data):
    # 2026-10-04 is Sunday
    slots = get_slots(clinic_data, "dr_rao", "2026-10-04")
    assert slots == []

def test_leave_closed(clinic_data):
    # Dr. Sethi on 2026-10-05
    slots = get_slots(clinic_data, "dr_sethi", "2026-10-05")
    assert slots == []

def test_occupied_removed(clinic_data):
    # Dr. Rao 2026-10-08 09:00 is absent because of ap_0015
    slots = get_slots(clinic_data, "dr_rao", "2026-10-08")
    assert "09:00" not in slots

def test_sorted_output(clinic_data):
    slots = get_slots(clinic_data, "dr_rao", "2026-10-07")
    assert slots == sorted(slots)
