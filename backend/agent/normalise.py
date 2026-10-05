import re
from datetime import datetime, timedelta
from typing import Dict, Any, Optional

WEEKDAYS = {
    "somwar": 0, "monday": 0,
    "mangalwar": 1, "tuesday": 1,
    "budhwar": 2, "wednesday": 2,
    "guruwar": 3, "thursday": 3,
    "shukrawar": 4, "friday": 4,
    "shanivaar": 5, "saturday": 5,
    "ravivar": 6, "sunday": 6
}

def normalise_date(text: str, today: str) -> Optional[str]:
    dt_today = datetime.strptime(today, "%Y-%m-%d")
    text_lower = text.lower()
    
    found_dates = []
    
    # Check tareekh e.g. "3 tareekh", "7 tareekh"
    tareekh_matches = list(re.finditer(r'(\d+)\s+tareekh', text_lower))
    for m in tareekh_matches:
        day = int(m.group(1))
        found_dates.append((m.start(), f"{dt_today.year}-{dt_today.month:02d}-{day:02d}"))
        
    # Relative
    for word, offset in [("aaj", 0), ("kal", 1), ("parso", 2), ("tomorrow", 1), ("today", 0)]:
        for m in re.finditer(rf'\b{word}\b', text_lower):
            target = dt_today + timedelta(days=offset)
            found_dates.append((m.start(), target.strftime("%Y-%m-%d")))
            
    # Weekdays
    for word, wd in WEEKDAYS.items():
        for m in re.finditer(rf'\b{word}\b', text_lower):
            days_ahead = wd - dt_today.weekday()
            if days_ahead <= 0:
                days_ahead += 7
            target = dt_today + timedelta(days=days_ahead)
            found_dates.append((m.start(), target.strftime("%Y-%m-%d")))
            
    if not found_dates:
        return None
        
    # Sort by position in text, last one wins
    found_dates.sort(key=lambda x: x[0])
    return found_dates[-1][1]

NUMBER_WORDS = {
    "ek": 1, "do": 2, "teen": 3, "char": 4, "chaar": 4, "paanch": 5, "panch": 5, "chhe": 6, "chhah": 6,
    "saat": 7, "aath": 8, "nau": 9, "das": 10, "gyarah": 11, "barah": 12, "baarah": 12,
}
_NUM = r"\d{1,2}|" + "|".join(sorted(NUMBER_WORDS, key=len, reverse=True))
_EVENING_WORDS = r"\b(shaam|sham|evening|raat|dopahar|afternoon)\b"
_MORNING_WORDS = r"\b(subah|morning)\b"


def _hour(token: str) -> int:
    return int(token) if token.isdigit() else NUMBER_WORDS[token]


def _to_24h(hour: int, text_lower: str) -> int:
    """Spoken hours carry no am or pm. Use the caller's own word if there is one.

    Without one, the clinic is never open before 09:00, so 1 to 7 can only mean the afternoon or evening.
    """
    if hour >= 12:
        return hour
    if re.search(_EVENING_WORDS, text_lower):
        return hour + 12
    if re.search(_MORNING_WORDS, text_lower):
        return hour
    return hour + 12 if 1 <= hour <= 7 else hour


def normalise_time(text: str) -> Optional[str]:
    """A concrete HH:MM if the caller gave one, else a 'morning' or 'evening' flag, else None.

    A concrete time always wins over a flag, whatever order they were said in. Among concrete times, the last wins.
    """
    text_lower = text.lower()
    concrete = []

    # exact matches like 9:30 or 3:15
    for m in re.finditer(r'\b(\d{1,2}):(\d{2})\b', text_lower):
        concrete.append((m.start(), f"{_to_24h(int(m.group(1)), text_lower):02d}:{m.group(2)}"))

    # "saadhe nau" = 9:30, "saadhe teen" = 15:30
    for m in re.finditer(rf'\bsaadhe\s+({_NUM})\b', text_lower):
        concrete.append((m.start(), f"{_to_24h(_hour(m.group(1)), text_lower):02d}:30"))

    # "dedh baje" = 1:30, "dhai baje" = 2:30
    for m in re.finditer(r'\b(dedh|dhai)\s+baje\b', text_lower):
        hour = 1 if m.group(1) == "dedh" else 2
        concrete.append((m.start(), f"{_to_24h(hour, text_lower):02d}:30"))

    # "10 baje", "gyarah baje", "teen baje". The number must not be the minutes of an H:MM time ("9:15 baje").
    for m in re.finditer(rf'(?<![\d:])\b({_NUM})\s+baje\b', text_lower):
        hour = _hour(m.group(1))
        if hour <= 23:
            concrete.append((m.start(), f"{_to_24h(hour, text_lower):02d}:00"))

    if concrete:
        concrete.sort(key=lambda x: x[0])
        return concrete[-1][1]

    flags = []
    for m in re.finditer(r'\b(subah|shaam|sham|morning|evening)\b', text_lower):
        flags.append((m.start(), "evening" if m.group(1) in ("shaam", "sham", "evening") else "morning"))
    if flags:
        flags.sort(key=lambda x: x[0])
        return flags[-1][1]
    return None

def normalise_phone(text: str) -> Optional[str]:
    # Strip spaces and dashes, look for 10 digits
    clean = re.sub(r'[\s\-]', '', text)
    matches = re.findall(r'\b\d{10}\b', clean)
    if matches:
        return matches[-1]
    return None
    
def extract_intent(text: str) -> Optional[str]:
    """Intent stated in this turn, or None. Never defaults to book.

    The conversation-level default is applied by the state machine, not here.
    """
    text_lower = text.lower()
    if "cancel" in text_lower:
        return "cancel"
    if "reschedule" in text_lower or "karwana hai" in text_lower and "aaj ka appointment" in text_lower:
        return "reschedule"
    if "appointment" in text_lower or "dikhana hai" in text_lower or "milna hai" in text_lower or "aa sakta hoon" in text_lower:
        return "book"
    return None


_RELATIVE_DATE_WORD = r"(?:kal|parso|aaj|tomorrow|today)"

def date_is_ambiguous(text: str) -> bool:
    """True when the caller offers two different relative dates, e.g. 'kal ya parso'."""
    text_lower = text.lower()
    pair = rf"\b{_RELATIVE_DATE_WORD}\b\s+(?:ya|or)(?:\s+phir)?\s+\b{_RELATIVE_DATE_WORD}\b"
    for m in re.finditer(pair, text_lower):
        first = re.search(_RELATIVE_DATE_WORD, m.group(0)).group(0)
        second = re.findall(_RELATIVE_DATE_WORD, m.group(0))[-1]
        if first != second:
            return True
    return False
    



def extract_doctor(text: str, clinic_data) -> Optional[str]:
    text_lower = text.lower()
    import re
    for doc_id, doc in clinic_data.doctors.items():
        doc_last_name = doc.name.split()[-1].lower()
        if re.search(r'\b' + re.escape(doc_last_name) + r'\b', text_lower) or doc.name.lower() in text_lower:
            return doc_id
    return None

def get_actor_and_target_name(text: str, clinic_data) -> tuple[Optional[str], Optional[str]]:
    text_lower = text.lower()
    import re
    found = []
    
    all_patients = list(clinic_data.patients.values())
    all_names = set()
    for p in all_patients:
        all_names.add(p.name)
        all_names.add(p.name.split()[0]) # First name
        all_names.add(p.name.split()[-1]) # Last name
        
    sorted_names = sorted(list(all_names), key=len, reverse=True)
    
    for n in sorted_names:
        pattern = r'\b' + re.escape(n.lower()) + r'\b'
        for m in re.finditer(pattern, text_lower):
            found.append((m.start(), n))
            
    if not found:
        return None, None
        
    found.sort(key=lambda x: x[0])
    
    filtered = []
    for f in found:
        if not any(other[0] <= f[0] and f[0] + len(f[1]) <= other[0] + len(other[1]) and other != f for other in found):
            filtered.append(f)
            
    if not filtered:
        return None, None
        
    if len(filtered) == 1:
        return filtered[0][1], filtered[0][1]
    
    return filtered[-1][1], filtered[0][1]
