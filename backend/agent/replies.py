"""Caller-facing reply templates.

Language is detected in code (no model). Templates are keyed by escalation reason or conversation need.
Emergency numbers are placeholders: filled from clinic.json if it has them, otherwise from config.
Nothing here gives medical advice, and no template contains a patient, doctor or appointment fact:
those are passed in from tool results.
"""
import json
import re
from datetime import date as _date
from typing import Optional

DEVANAGARI = re.compile(r"[\u0900-\u097F]")
HINGLISH_MARKERS = {
    "hai", "hain", "hoon", "tha", "thi", "mein", "main", "mujhe", "aur", "ya", "nahi", "nahin", "kya", "kab",
    "kaise", "chahiye", "chahie", "baje", "kal", "parso", "aaj", "abhi", "raha", "rahi", "karna", "karo",
    "kijiye", "ke", "ka", "ki", "ko", "se", "saath", "subah", "shaam", "dard", "seene", "saans", "pet",
    "bukhar", "goli", "dawai", "lun", "ji", "bas", "yahi", "poochna", "unka", "padosi", "mera", "meri",
}


def detect_language(text: str) -> str:
    """'hi' (Hinglish/Devanagari) or 'en'. Deterministic, no model."""
    if DEVANAGARI.search(text):
        return "hi"
    words = re.findall(r"[a-z]+", text.lower())
    return "hi" if any(w in HINGLISH_MARKERS for w in words) else "en"


def emergency_numbers(clinic_path: Optional[str]) -> tuple:
    """(primary, ambulance). clinic.json first (key 'emergency' or 'emergency_number'), then config."""
    from config import EMERGENCY_PRIMARY, EMERGENCY_AMBULANCE
    primary, ambulance = EMERGENCY_PRIMARY, EMERGENCY_AMBULANCE
    try:
        with open(clinic_path, encoding="utf-8") as f:
            raw = json.load(f)
        em = raw.get("emergency") or raw.get("emergency_number")
        if isinstance(em, dict):
            primary = em.get("primary", primary)
            ambulance = em.get("ambulance", ambulance)
        elif em:
            primary = str(em)
    except Exception:
        pass
    return primary, ambulance


# Keyed by escalation reason. {primary} and {ambulance} are filled at render time.
ESCALATION = {
    "clinical_urgent": {
        "en": "A human is connecting. If symptoms are severe or worsening, call the emergency number now at {primary} or {ambulance}. I cannot provide medical advice.",
        "hi": "Main abhi aapko clinic staff se connect kar rahi hoon. Agar yeh emergency hai, turant {primary} ya {ambulance} par call kijiye.",
    },
    "medical_advice": {
        "en": "A human is connecting. I cannot provide medical advice.",
        "hi": "Dawai ke baare mein main salah nahi de sakti, yeh doctor hi bata sakte hain. Main aapko clinic staff se connect kar rahi hoon.",
    },
    "not_authorised": {
        "en": "A human is connecting to verify authorization.",
        "hi": "Main is record mein aapki taraf se badlav nahi kar sakti. Main aapko clinic staff se connect kar rahi hoon.",
    },
    "ambiguous_patient": {
        "en": "A human is connecting to assist with finding your details.",
        "hi": "Mujhe pakka nahi ho paya ki aapka record kaun sa hai. Main aapko clinic staff se connect kar rahi hoon.",
    },
    "out_of_scope": {
        "en": "A human is connecting to help you with this request.",
        "hi": "Main is request mein madad nahi kar sakti. Main aapko clinic staff se connect kar rahi hoon.",
    },
}

PROMPTS = {
    "refused": {
        "en": "Sorry, I cannot help with that request.",
        "hi": "Maaf kijiye, main is request mein madad nahi kar sakti.",
    },
    "ask_no_match": {
        "en": "I could not find a matching record. May I have the full name or phone number?",
        "hi": "Mujhe record nahi mila. Kripya poora naam ya phone number batayein.",
    },
    "ack_match": {
        "en": "I found the record. ",
        "hi": "Record mil gaya hai. ",
    },
    "ask_intent": {
        "en": "How can I help you today? I can book, reschedule or cancel an appointment.",
        "hi": "Main aapki kya madad kar sakti hoon? Main appointment book, reschedule ya cancel kar sakti hoon.",
    },
    "ask_intent_2": {
        "en": "Please tell me what you would like to do.",
        "hi": "Kripya batayen ki aap kya karna chahte hain.",
    },
    "ask_patient": {
        "en": "May I have the patient's full name or phone number?",
        "hi": "Kripya patient ka poora naam ya phone number batayein.",
    },
    "ask_patient_2": {
        "en": "Please provide the patient's full name or phone number to proceed.",
        "hi": "Aage badhne ke liye kripya patient ka poora naam ya phone number batayein.",
    },
    "ask_more_identity": {
        "en": "More than one record matches. Could you share the full name or date of birth?",
        "hi": "Ek se zyada record mil rahe hain. Kripya poora naam ya janm tithi batayein.",
    },
    "ask_doctor": {
        "en": "Which doctor would you like to see?",
        "hi": "Aap kis doctor se milna chahte hain?",
    },
    "ask_date": {
        "en": "Which day would you like?",
        "hi": "Aapko kis din ka appointment chahiye?",
    },
    "ask_date_2": {
        "hi": "Kripya appointment ki tareekh batayen.",
        "en": "Please tell me the date for the appointment."
    },
    "ask_date_choice": {
        "en": "Which one would you like, a single day please?",
        "hi": "Kaunsi tareekh chahiye? Kripya ek hi din batayein.",
    },
    "ask_time": {
        "en": "What time would you prefer?",
        "hi": "Aapko kis samay ka appointment chahiye?",
    },
    "ask_intent_known": {
        "en": "Would you like to book, reschedule or cancel an appointment?",
        "hi": "Aap appointment book, reschedule ya cancel karna chahte hain?",
    },
    "ask_more_identity_2": {
        "en": "I still cannot tell which record is yours. If you can share a phone number or date of birth, please do. Otherwise I will connect you to the clinic staff.",
        "hi": "Mujhe abhi bhi pakka nahi ho raha ki aapka record kaun sa hai. Agar phone number ya janm tithi yaad ho to batayein, warna main aapko clinic staff se connect kar dungi.",
    },
    "ask_verify": {
        "en": "To continue, please tell me your own full name and registered phone number.",
        "hi": "Aage badhne ke liye kripya apna poora naam aur registered phone number batayein.",
    },
    "ask_phone_only": {
        "en": "Please share your own registered phone number so I can check who is calling.",
        "hi": "Kripya apna registered phone number batayein, taaki main confirm kar sakoon ki aap kaun hain.",
    },
    "ready": {
        "en": "Thank you. I am checking this now.",
        "hi": "Dhanyavaad. Main abhi ise check kar rahi hoon.",
    },
    "still_need": {
        "en": "Sorry, I still need this: ",
        "hi": "Maaf kijiye, mujhe yeh jaankari abhi bhi chahiye: ",
    },
    "none": {
        "en": "I could not complete this request.",
        "hi": "Main yeh request poori nahi kar paayi.",
    },
}

DONE = {
    "booked": {
        "en": "Your appointment with {doctor} is booked for {date} at {time}. Reference: {appt}.",
        "hi": "Aapka appointment {doctor} ke saath {date} ko {time} baje book ho gaya hai. Reference: {appt}.",
    },
    "rescheduled": {
        "en": "Your appointment {appt} has been moved to {date} at {time}.",
        "hi": "Aapka appointment {appt} {date} ko {time} baje ke liye badal diya gaya hai.",
    },
    "cancelled": {
        "en": "Your appointment {appt} has been cancelled.",
        "hi": "Aapka appointment {appt} cancel kar diya gaya hai.",
    },
}


def _nice_date(iso: Optional[str]) -> str:
    try:
        d = _date.fromisoformat(iso)
        return f"{d.day} {d.strftime('%b %Y')}"
    except Exception:
        return iso or ""


SLOTS = {
    "offer": {
        "en": "{doctor} has these free slots on {date}: {slots}. Which one suits you?",
        "hi": "{doctor} ke saath {date} ko khali slots: {slots}. Kaun sa theek rahega?",
    },
    "free": {
        "en": "{time} is free. ",
        "hi": "{time} khali hai. ",
    },
    "taken": {
        "en": "{time} is not free. {doctor} has these free slots on {date}: {slots}. Which one suits you?",
        "hi": "{time} khali nahi hai. {doctor} ke saath {date} ko khali slots: {slots}. Kaun sa theek rahega?",
    },
    "none": {
        "en": "{doctor} has no free slots on {date}. Please tell me another day.",
        "hi": "{doctor} ke saath {date} ko koi slot khali nahi hai. Kripya koi aur din batayein.",
    },
    "none_time": {
        "en": "{doctor} has no free slots on {date}, so {time} cannot be booked. Please tell me another day.",
        "hi": "{doctor} ke saath {date} ko koi slot khali nahi hai, isliye {time} par booking nahi ho sakti. Kripya koi aur din batayein.",
    },
}
MAX_OFFERED = 4

# Said in front of a slot message that repeats because the caller added nothing new.
REPEAT_SLOTS = {
    "none": {"en": "I understand, but ", "hi": "Ji, lekin "},
    "offer": {"en": "Sure. ", "hi": "Ji. "},
}


def _slot_offer(m, lang: str) -> str:
    """What the schedule says for the doctor and day the caller asked about. Built only from the search_slots result.

    Returns '' when there is nothing to say yet, or when the requested time is free and the next question is about the patient.
    """
    if m.intent != "book" or not m.doctor_id or not m.date:
        return ""
    result = getattr(m, "searches", {}).get((m.doctor_id, m.date))
    if not result or not result.get("ok"):
        return ""
    doc = m.clinic_data.doctors.get(m.doctor_id)
    fields = {"doctor": doc.name if doc else "", "date": _nice_date(m.date), "time": m.time or ""}
    slots = result.get("slots", [])
    concrete = bool(m.time) and m.time not in ("morning", "evening")

    if not slots:
        return SLOTS["none_time" if concrete else "none"][lang].format(**fields)

    if concrete:
        if m.time in slots:
            known_patient = m.patient_id or m.target_name or m.phone
            return "" if known_patient else SLOTS["free"][lang].format(**fields) + PROMPTS["ask_patient"][lang]
        nearest = sorted(slots, key=lambda s: abs(_minutes(s) - _minutes(m.time)))[:MAX_OFFERED]
        fields["slots"] = ", ".join(sorted(nearest))
        return SLOTS["taken"][lang].format(**fields)

    pool = slots
    if m.time == "morning":
        pool = [s for s in slots if _minutes(s) < 12 * 60] or slots
    elif m.time == "evening":
        pool = [s for s in slots if _minutes(s) >= 16 * 60] or slots
    fields["slots"] = ", ".join(pool[:MAX_OFFERED])
    return SLOTS["offer"][lang].format(**fields)


def _minutes(hhmm: str) -> int:
    h, mm = hhmm.split(":")
    return int(h) * 60 + int(mm)


def _known_facts(m, lang: str) -> str:
    """What the caller has told us so far, built only from resolved state (never invented)."""
    parts = []
    doc = m.clinic_data.doctors.get(m.doctor_id) if m.doctor_id else None
    if doc:
        parts.append(doc.name)
    if m.date:
        parts.append(_nice_date(m.date))
    if m.time:
        parts.append(m.time)
    if not parts:
        return ""
    return ("Theek hai, " if lang == "hi" else "Noted: ") + ", ".join(parts) + ". "


def reply_for(m) -> str:
    """Reply for the machine's current state, in the caller's language.

    Terminal replies (handoff, refusal, done) are returned as they are. Replies that ask the caller
    for something never repeat the previous reply word for word: they acknowledge what is now known,
    or say so plainly when nothing new was learned.
    """
    lang = detect_language(m.all_text)
    history = m.__dict__.setdefault("reply_history", [])
    draft = _draft_reply(m, lang)
    terminal = m.terminal_state in ("escalated", "refused") or m.terminal_state in DONE
    if not terminal and history and draft == history[-1]:
        draft = _varied(m, lang, draft, history[-1])
    history.append(draft)
    return draft


def _varied(m, lang: str, draft: str, previous: str) -> str:
    # Asked twice for patient details with several matches: the next step is a person, so say that.
    if draft == PROMPTS["ask_more_identity"][lang]:
        return PROMPTS["ask_more_identity_2"][lang]
    # The schedule has not changed. Say so, rather than echoing facts the message already contains.
    if "slot" in draft:
        none_left = "koi slot khali nahi" in draft or "no free slots" in draft
        return REPEAT_SLOTS["none" if none_left else "offer"][lang] + draft
    candidates = []
    facts = _known_facts(m, lang)
    if facts:
        candidates.append(facts + draft)
    candidates.append(PROMPTS["still_need"][lang] + draft)
    for c in candidates:
        if c != previous:
            return c
    return PROMPTS["still_need"][lang] + draft


def _draft_reply(m, lang: str) -> str:
    state = m.terminal_state

    if state == "escalated":
        tpl = ESCALATION.get(m.escalation_reason) or ESCALATION["out_of_scope"]
        primary, ambulance = emergency_numbers(getattr(m, "clinic_path", None))
        return tpl[lang].format(primary=primary, ambulance=ambulance)
    if state == "refused":
        return PROMPTS["refused"][lang]
    if state in DONE:
        last = next((c for c in reversed(m.tool_calls) if c["name"] in
                     ("book_appointment", "reschedule_appointment", "cancel_appointment")
                     and c["result"] and c["result"].get("ok")), None)
        args = last["arguments"] if last else {}
        doc = m.clinic_data.doctors.get(args.get("doctor_id") or m.doctor_id)
        return DONE[state][lang].format(
            doctor=doc.name if doc else "", date=_nice_date(args.get("date") or m.date),
            time=args.get("start") or m.time or "", appt=m.appointment_id or "")


    last = m.tool_calls[-1] if m.tool_calls else None
    
    prefix = ""
    if last and last["name"] == "lookup_patient" and last.get("result"):
        status = last["result"].get("status")
        if status == "none":
            return PROMPTS["ask_no_match"][lang]
        elif status == "match":
            prefix = PROMPTS["ack_match"][lang]

    if m.date_ambiguous:
        return prefix + PROMPTS["ask_date_choice"][lang]
    offer = _slot_offer(m, lang)
    if offer:
        return prefix + offer
    if m.candidates and not m.patient_id:
        return prefix + PROMPTS["ask_more_identity"][lang]
    if m.intent is None:
        # Nothing usable about what the caller wants yet.
        if m.target_name or m.phone or m.doctor_id:
            return prefix + PROMPTS["ask_intent_known"][lang]
        return prefix + PROMPTS["ask_intent"][lang]
    booking_details_missing = m.intent == "book" and (not m.doctor_id or not m.date)
    if not m.patient_id and not (m.target_name or m.phone) and not booking_details_missing:
        return prefix + PROMPTS["ask_patient"][lang]
    if m.intent in ("cancel", "reschedule") and m.patient_id:
        # Never confirm whose record this is. Ask the caller to identify themselves instead.
        if m.intent == "reschedule":
            if not m.date:
                return prefix + PROMPTS["ask_date"][lang]
            if not m.time:
                return prefix + PROMPTS["ask_time"][lang]
        if not m.phone:
            someone_else = bool(m.actor_name and m.target_name and m.actor_name != m.target_name)
            return PROMPTS["ask_phone_only" if someone_else else "ask_verify"][lang]
        return PROMPTS["ready"][lang]
    if m.intent in ("book", "reschedule"):
        if m.intent == "book" and not m.doctor_id:
            return prefix + PROMPTS["ask_doctor"][lang]
        if not m.date:
            return prefix + PROMPTS["ask_date"][lang]
        if not m.time:
            return prefix + PROMPTS["ask_time"][lang]
    return prefix + PROMPTS["ready"][lang]


def safe_reply(m) -> str:
    """Used when a drafted reply would state a fact no tool returned."""
    return PROMPTS['none'][detect_language(m.all_text)]

