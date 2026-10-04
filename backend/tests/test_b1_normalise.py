import pytest
from agent.normalise import normalise_date, normalise_time

def test_table_driven_dates():
    assert normalise_date("Shanivaar", "2026-10-01") == "2026-10-03"
    assert normalise_date("kal", "2026-10-01") == "2026-10-02"
    assert normalise_date("parso", "2026-10-01") == "2026-10-03"
    
def test_table_driven_times():
    assert normalise_time("gyarah baje") == "11:00"
    assert normalise_time("9 baje") == "09:00"
    assert normalise_time("shaam") == "evening"
    
def test_correction():
    assert normalise_date("Mangalwar 6 tareekh... nahi, budhwar 7 tareekh", "2026-10-01") == "2026-10-07"
    
def test_date_stability():
    assert normalise_date("kal", "2026-10-01") == "2026-10-02"
    assert normalise_date("kal", "2026-10-15") == "2026-10-16"
