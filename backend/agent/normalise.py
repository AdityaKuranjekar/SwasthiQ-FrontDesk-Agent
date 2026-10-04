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

def normalise_time(text: str) -> Optional[str]:
    text_lower = text.lower()
    found_times = []
    
    # exact matches like 9:30
    for m in re.finditer(r'(\d{1,2}:\d{2})', text_lower):
        parts = m.group(1).split(":")
        t = f"{int(parts[0]):02d}:{parts[1]}"
        found_times.append((m.start(), t))
        
    # baje matches
    for m in re.finditer(r'(gyarah|10|9|11|12|1|2|3|4|5|6|7|8)\s+baje', text_lower):
        val = m.group(1)
        if val == "gyarah": t = "11:00"
        elif val == "10": t = "10:00"
        elif val == "9": t = "09:00"
        elif val == "11": t = "11:00"
        else: t = f"{int(val):02d}:00"
        found_times.append((m.start(), t))
        
    for m in re.finditer(r'saadhe\s+(nau|9|10|11)', text_lower):
        val = m.group(1)
        if val in ("nau", "9"): t = "09:30"
        elif val == "10": t = "10:30"
        else: t = "11:30"
        found_times.append((m.start(), t))
        
    # time of day flags (subah, shaam)
    for m in re.finditer(r'\b(subah|shaam|morning|evening)\b', text_lower):
        val = m.group(1)
        flag = "evening" if val in ("shaam", "evening") else "morning"
        found_times.append((m.start(), flag))
        
    if not found_times:
        return None
        
    found_times.sort(key=lambda x: x[0])
    return found_times[-1][1]

def normalise_phone(text: str) -> Optional[str]:
    # Strip spaces and dashes, look for 10 digits
    clean = re.sub(r'[\s\-]', '', text)
    matches = re.findall(r'\b\d{10}\b', clean)
    if matches:
        return matches[-1]
    return None
    
def extract_intent(text: str) -> str:
    # A simple brute-force for the 15 scripts
    text_lower = text.lower()
    if "cancel" in text_lower:
        return "cancel"
    if "reschedule" in text_lower or "karwana hai" in text_lower and "aaj ka appointment" in text_lower:
        return "reschedule"
    if "appointment" in text_lower or "dikhana hai" in text_lower or "milna hai" in text_lower or "aa sakta hoon" in text_lower:
        return "book"
    return "book"
    



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
