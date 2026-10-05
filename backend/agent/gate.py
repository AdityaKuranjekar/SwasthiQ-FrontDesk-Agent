from typing import Optional, List
from dataclasses import dataclass, field
import re


@dataclass
class GateResult:
    kind: str
    reason: Optional[str]
    rule_id: Optional[str] = None
    # Human-readable symptom phrases for the escalation summary, e.g. ["chest pain", "breathlessness"].
    symptoms: List[str] = field(default_factory=list)


def edit_dist(s1: str, s2: str) -> int:
    if len(s1) < len(s2): return edit_dist(s2, s1)
    if len(s2) == 0: return len(s1)
    prev_row = range(len(s2) + 1)
    for i, c1 in enumerate(s1):
        curr_row = [i + 1]
        for j, c2 in enumerate(s2):
            ins = prev_row[j + 1] + 1
            dele = curr_row[j] + 1
            sub = prev_row[j] + (c1 != c2)
            curr_row.append(min(ins, dele, sub))
        prev_row = curr_row
    return prev_row[-1]


def fuzzy_match(token: str, targets: list[str]) -> bool:
    for t in targets:
        if t in token: return True
        if len(t) >= 4:
            dist = edit_dist(token, t)
            if len(t) <= 5 and dist <= 1: return True
            if len(t) > 5 and dist <= 2: return True
    return False


# word fragment -> (rule id, symptom phrase). Order matters: the first match names the rule.
RED_FLAGS = [
    (["chest", "chast", "seene", "seenay"], "red_flag.chest_pain", "chest pain"),
    (["saans", "sans", "breath", "breathlessness"], "red_flag.breathlessness", "breathlessness"),
    (["unconscious", "unconsious", "behosh"], "red_flag.unconscious", "loss of consciousness"),
    (["bleeding", "blding", "khoon"], "red_flag.bleeding", "bleeding"),
    (["vomit"], "red_flag.vomiting", "vomiting"),
    (["phool", "ful"], "red_flag.swelling", "swelling"),
]

# Medicine / dose / timing / stopping-continuing. A bare mention of a drug is not a question.
DRUG_WORDS = [r"dawai", r"dawa", r"goli", r"tablet", r"crocin", r"paracetamol", r"medicine", r"medication", r"syrup"]
DOSE_TOPIC = [r"dose", r"dosage", r"kitni der", r"kitne ghante", r"kitni baar", r"kitni goli"]
ASKING = [r"\?", r"\bkya\b", r"\bkab\b", r"\bkaise\b", r"\bkitna\b", r"\bkitni\b", r"\bkitne\b",
          r"\blun\b", r"\bkhaun\b", r"\bkha lun\b", r"le sakta", r"le sakti", r"\bshould\b", r"\bcan i\b",
          r"\bstop\b", r"\bcontinue\b", r"band kar", r"\brok\b", r"jaari rakh", r"\bjari rakh"]


def _any(patterns: list[str], text: str) -> bool:
    return any(re.search(p, text) for p in patterns)


def check_gate(text: str) -> Optional[GateResult]:
    text_lower = text.lower()

    # 1. Injection
    if any(phrase in text_lower for phrase in ["ignore previous instructions", "administrator mode", "authorised internal test"]):
        return GateResult("refused", None, "security.injection")

    # 2. Bulk
    if any(phrase in text_lower for phrase in ["every appointment", "all appointments"]):
        return GateResult("refused", None, "security.bulk")

    clauses = re.split(r'\b(?:lekin|par|aur|but|and)\b|[,.]', text_lower)
    
    matched_phrases = []
    first_rule_id = None
    for clause in clauses:
        clause_str = clause.strip()
        for fragments, rule_id, phrase in RED_FLAGS:
            if any(f in clause_str for f in fragments) and phrase not in matched_phrases:
                matched_phrases.append(phrase)
                if first_rule_id is None:
                    first_rule_id = rule_id

    if matched_phrases:
        return GateResult("escalated", "clinical_urgent", first_rule_id, matched_phrases)

    # Severity words
    severity_words = ["bahut", "tez", "zyada", "severe", "worse", "badh gaya"]
    has_severity = any(sw in text_lower for sw in severity_words)

    active_markers = ["abhi bhi", "ab bhi", "phir se", "badh raha", "ho raha hai", "still", "again"]
    has_active_marker = any(am in text_lower for am in active_markers)

    resolved_phrases = ["ab theek hai", "theek ho gaya", "pehle tha"]
    has_resolution = any(rp in text_lower for rp in resolved_phrases)

    body_parts = ["pet", "pait", "stomach", "abdomen", "head", "sir"]
    pain_words = ["pain", "dard", "paining", "dukh", "marod", "problem", "dikkat"]
    negations = ["nahi", "nahin", "no", "not"]

    trigger_clause = None
    for clause in clauses:
        clause_str = clause.strip()
        tokens = re.findall(r'\w+', clause_str)
        has_body = any(fuzzy_match(tk, body_parts) for tk in tokens)
        has_pain = any(fuzzy_match(tk, pain_words) for tk in tokens)
        if has_body and has_pain:
            is_negated = any(neg in tokens for neg in negations)
            matched_bp = "body"
            for tk in tokens:
                for bp in body_parts:
                    if edit_dist(tk, bp) <= 1:
                        matched_bp = bp
            phrase = f"{matched_bp} pain"
            if matched_bp in ["pet", "pait", "stomach", "abdomen"]: phrase = "stomach pain"
            elif matched_bp in ["sir", "head"]: phrase = "headache"
            
            if has_severity:
                return GateResult("escalated", "clinical_urgent", "red_flag.severe_pain", [f"severe {phrase}"])
            if is_negated:
                continue
            trigger_clause = phrase

    if trigger_clause is not None:
        if has_resolution and not has_active_marker:
            pass
        else:
            return GateResult("escalated", "clinical_urgent", "red_flag.body_pain", [trigger_clause])

    # 3. Medical advice: only when the caller ASKS about a medicine, a dose, timing, or stopping/continuing.
    # "Do din se bukhar hai" (symptom alone) and "Crocin le raha hoon" (statement) do not escalate.
    asks = _any(ASKING, text_lower)
    if _any(DOSE_TOPIC, text_lower) or (_any(DRUG_WORDS, text_lower) and asks):
        return GateResult("escalated", "medical_advice", "advice.dosage_question")

    return None