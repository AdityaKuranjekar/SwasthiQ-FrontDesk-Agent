"""Plain-language one-line descriptions of tool results, for the UI transcript.

Built only from what the tool layer returned. Never invents a value: a failed call shows its error code.
"""
from datetime import date as _date


def day_label(iso: str) -> str:
    try:
        d = _date.fromisoformat(iso)
        return f"{d.strftime('%a')} {d.day} {d.strftime('%b')}"
    except Exception:
        return iso or ""


def ticket_label(ticket_id) -> str:
    """The tool layer returns the handoff row id as an integer; shown as tk_0001."""
    try:
        return f"tk_{int(ticket_id):04d}"
    except (TypeError, ValueError):
        return str(ticket_id)


def describe_result(name: str, args: dict, result) -> str:
    if not isinstance(result, dict):
        return "no result returned"
    if not result.get("ok"):
        err = result.get("error") or {}
        return f"error {err.get('code', 'failed')}"

    if name == "lookup_patient":
        status = result.get("status")
        if status == "match":
            p = result["patient"]
            return f"match: {p['id']} {p['name']}"
        if status == "candidates":
            ps = result.get("patients", [])
            return f"{len(ps)} candidates: " + ", ".join(f"{p['id']} {p['name']}" for p in ps)
        return "no match"
    if name == "search_slots":
        slots = result.get("slots", [])
        if not slots:
            return "0 slots"
        shown = ", ".join(slots[:6]) + (f", +{len(slots) - 6} more" if len(slots) > 6 else "")
        return f"{len(slots)} slots: {shown}"
    if name == "book_appointment":
        return f"booked {result.get('appointment_id')}, {day_label(args.get('date'))} {args.get('start', '')}".strip()
    if name == "reschedule_appointment":
        return f"rescheduled {result.get('appointment_id')}, {day_label(args.get('date'))} {args.get('start', '')}".strip()
    if name == "cancel_appointment":
        return f"cancelled {result.get('appointment_id')}"
    if name == "escalate_to_human":
        return f"ticket {ticket_label(result.get('ticket_id'))}"
    return "ok"
