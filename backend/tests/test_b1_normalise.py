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
    
@pytest.mark.parametrize("text,expected", [
    ("Subah 10 baje.", "10:00"),
    ("10 baje subah", "10:00"),             # a concrete time wins over the flag, in either order
    ("shaam 6 baje", "18:00"),               # the caller said evening
    ("teen baje", "15:00"),                  # clinic is never open at 3 am
    ("3 baje", "15:00"),
    ("subah 9 baje", "09:00"),
    ("nau baje", "09:00"),
    ("das baje", "10:00"),
    ("barah baje", "12:00"),
    ("saadhe nau", "09:30"),
    ("saadhe teen", "15:30"),
    ("dedh baje", "13:30"),
    ("dhai baje", "14:30"),
    ("9:15 baje", "09:15"),                  # the 15 is minutes, not "15 baje"
    ("somwar subah 9:15 baje", "09:15"),
    ("3:30 baje", "15:30"),
    ("9:30", "09:30"),
    ("3:15", "15:15"),
    ("dopahar 2 baje", "14:00"),
    ("subah", "morning"),
    ("shaam", "evening"),
    ("koi bhi time chalega", None),
])
def test_time_phrases(text, expected):
    assert normalise_time(text) == expected


def test_a_date_number_is_not_a_time():
    # "8 tareekh" is a date; only "baje" makes a number a time.
    assert normalise_time("8 tareekh ko shaam ko") == "evening"
    assert normalise_time("8 tareekh subah 9 baje") == "09:00"


def test_correction():
    assert normalise_date("Mangalwar 6 tareekh... nahi, budhwar 7 tareekh", "2026-10-01") == "2026-10-07"
    
def test_date_stability():
    assert normalise_date("kal", "2026-10-01") == "2026-10-02"
    assert normalise_date("kal", "2026-10-15") == "2026-10-16"
