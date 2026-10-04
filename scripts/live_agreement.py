import os, sys, json, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

import config
from agent.machine import AgentMachine
from agent.llm import clear_llm_cache
from config import CLINIC_FILE
from dotenv import load_dotenv

def process_file(file_path, key, extract_mode):
    if key:
        os.environ["GEMINI_API_KEY"] = key
    else:
        if "GEMINI_API_KEY" in os.environ:
            del os.environ["GEMINI_API_KEY"]
            
    config.EXTRACT_MODE = extract_mode
    clear_llm_cache()
    
    with open(file_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
        
    machine = AgentMachine(CLINIC_FILE, ":memory:", data["today"])
    turns = data["turns"]
    for i, turn in enumerate(turns):
        machine.is_last_turn = (i == len(turns) - 1)
        machine.process_turn(turn)
        if extract_mode == "always" and key:
            time.sleep(4.5)  # Pace to 12 RPM max (1 request every 5s)
        
    res = machine.finalize()
    
    extracted_fields = {
        "intent": machine.intent,
        "date": machine.date,
        "time": machine.time,
        "actor_name": machine.actor_name,
        "target_name": machine.target_name,
        "doctor_id": machine.doctor_id
    }
    
    machine.conn.close()
    
    t_state = res.get("terminal_state")
    e_reason = res.get("escalation_reason")
    tools = tuple(sorted([t["name"] for t in res.get("tool_calls", [])]))
    
    m = res.get("metrics", {})
    metrics = {
        "turns": m.get("turns", len(turns)),
        "attempts": m.get("model_attempts", 0),
        "success": m.get("model_success", 0),
        "rate_limited": m.get("model_rate_limited", 0),
        "invalid": m.get("model_invalid", 0),
        "error": m.get("model_error", 0)
    }
    
    return t_state, e_reason, tools, metrics, extracted_fields

def main():
    backend_dir = Path(__file__).parent.parent / "backend"
    load_dotenv(backend_dir / ".env")
    
    real_key = os.environ.get("GEMINI_API_KEY")
    if not real_key:
        print("ERROR: GEMINI_API_KEY is not set in backend/.env")
        sys.exit(1)
        
    cv_dir = Path(__file__).parent.parent / "conversations"
    files = sorted(list(cv_dir.glob("cv_*.json")))
    
    differing = False
    
    print(f"{'Script':<12} | {'Trn':<3} | {'Atmpt':<5} | {'Succ':<4} | {'RLim':<4} | {'Inv':<3} | {'Err':<3} | {'Status'}")
    print("-" * 75)
    
    results = []
    
    for f in files:
        fname = f.name
        l_state, l_reason, l_tools, l_met, l_fields = process_file(f, real_key, "always")
        r_state, r_reason, r_tools, r_met, r_fields = process_file(f, None, "auto")
        
        status = "MATCH"
        if l_met["success"] < l_met["turns"]:
            # Red-flag turn might skip LLM entirely? Wait. 
            # If the red-flag gate triggers on turn 1, process_turn returns early. 
            # The model is not attempted. We should check if success == attempts.
            # But the user said: "A script only counts toward agreement if every turn got a successful answer."
            # Actually, if attempts < turns (due to early escalation), the model was successfully called for all ATTEMPTED turns.
            # Let's use: if l_met["success"] < l_met["turns"]: "not compared"
            if l_met["success"] < l_met["turns"]:
                status = "not compared"
        
        if status != "not compared":
            if (l_state, l_reason, l_tools) != (r_state, r_reason, r_tools):
                status = "DIFFERS (terminal)"
                differing = True
            elif l_fields != r_fields:
                status = "DIFFERS (fields)"
                differing = True
        
        print(f"{fname:<12} | {l_met['turns']:<3} | {l_met['attempts']:<5} | {l_met['success']:<4} | {l_met['rate_limited']:<4} | {l_met['invalid']:<3} | {l_met['error']:<3} | {status}")
        results.append((fname, l_fields, r_fields, l_state, l_reason, l_tools, r_state, r_reason, r_tools, status))
        
    print("\n")
    if differing:
        print("AGREEMENT FAILED.")
        for r in results:
            if "DIFFERS" in r[9]:
                print(f"\n--- {r[0]} ---")
                print(f"Status: {r[9]}")
                print(f"Live Fields: {r[1]}")
                print(f"Rule Fields: {r[2]}")
                print(f"Live Terminal: {r[3]}/{r[4]}/{r[5]}")
                print(f"Rule Terminal: {r[6]}/{r[7]}/{r[8]}")
        sys.exit(1)
    else:
        print("ALL COMPARED SCRIPTS AGREE.")
        
    print("\nVerifying 'auto' default makes 0 model calls:")
    auto_calls_total = 0
    for f in files:
        _, _, _, a_met, _ = process_file(f, real_key, "auto")
        auto_calls_total += a_met["attempts"]
    print(f"Total model calls in 'auto' mode across all scripts: {auto_calls_total}")
    field_comparison(files, real_key)



def field_comparison(files, real_key):
    """Per-turn comparison of raw model extraction vs raw rule extraction.
    Turn text, names and phone numbers are never printed."""
    import re
    from agent.gate import check_gate
    from agent.llm import extract_with_llm, _CACHE
    from agent.normalise import (normalise_date, normalise_time, extract_intent,
                                 extract_doctor, get_actor_and_target_name, date_is_ambiguous)
    from tools.data import load_clinic_data
    from config import DAILY_TOKEN_CAP

    os.environ["GEMINI_API_KEY"] = real_key
    clinic = load_clinic_data(CLINIC_FILE)
    fields = ["intent", "date", "time", "name", "doctor"]

    def show(field, v):
        if v is None:
            return "None"
        if field == "name":
            return "<name>"
        return re.sub(r"\d{8,}", "<phone>", str(v))

    print("\nFIELD-LEVEL COMPARISON (model vs rules, per turn)")
    print("-" * 75)
    for f in files:
        data = json.load(open(f, encoding="utf-8"))
        today, turns = data["today"], data["turns"]
        if any(check_gate(t) for t in turns):
            print(f"{f.name}: not compared (rule gate trips on a turn; model not called)")
            continue
        counts = {k: 0 for k in fields}
        diffs = []
        ok = True
        for i, t in enumerate(turns, 1):
            before = len(_CACHE)
            parsed, _, _, err = extract_with_llm(t, clinic, DAILY_TOKEN_CAP, 0)
            if len(_CACHE) != before:
                time.sleep(4.5)
            if parsed is None:
                ok = False
                break
            actor, target = get_actor_and_target_name(t, clinic)
            rname = target or actor
            # Same ambiguity rule as the state machine: an ambiguous date is no date, on either side.
            ambiguous = date_is_ambiguous(t)
            rules = {
                "intent": extract_intent(t),
                "date": None if ambiguous else normalise_date(t, today),
                "time": normalise_time(t),
                "name": rname,
                "doctor": extract_doctor(t, clinic),
            }
            model = {
                "intent": parsed.intent.value if parsed.intent else None,
                "date": None if (ambiguous or not parsed.date_phrase) else normalise_date(parsed.date_phrase, today),
                "time": normalise_time(parsed.time_phrase) if parsed.time_phrase else None,
                "name": parsed.patient_name,
                "doctor": parsed.doctor.value if parsed.doctor else None,
            }
            # rules report "unknown" when they find no intent
            if rules["intent"] == "unknown": rules["intent"] = None
            if model["intent"] == "other": model["intent"] = None
            for k in fields:
                a, b = rules[k], model[k]
                if k == "name":
                    a = a.strip().lower() if a else None
                    b = b.strip().lower() if b else None
                if a != b:
                    counts[k] += 1
                    diffs.append((i, k, show(k, rules[k]), show(k, model[k])))
        if not ok:
            print(f"{f.name}: not compared (model answer missing: {err})")
            continue
        print(f"{f.name}: " + " ".join(f"{k}={counts[k]}" for k in fields))
        for i, k, a, b in diffs:
            print(f"    turn {i} {k}: rules={a} model={b}")

if __name__ == '__main__':
    main()



