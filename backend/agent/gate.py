from typing import Optional
from dataclasses import dataclass
import re

@dataclass
class GateResult:
    kind: str
    reason: Optional[str]

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

def check_gate(text: str) -> Optional[GateResult]:
    text_lower = text.lower()
    
    # 1. Injection
    if any(phrase in text_lower for phrase in ["ignore previous instructions", "administrator mode", "authorised internal test"]):
        return GateResult("refused", None)
        
    # 2. Bulk
    if any(phrase in text_lower for phrase in ["every appointment", "all appointments"]):
        return GateResult("refused", None)
        
    # Red flags / severe conditions check first
    red_flags = ["khoon", "vomit", "behosh", "chest", "chast", "seene", "seenay", 
                 "saans", "sans", "breath", "breathlessness", "unconscious", 
                 "unconsious", "bleeding", "blding", "phool", "ful"]
                 
    if any(rf in text_lower for rf in red_flags):
        return GateResult("escalated", "clinical_urgent")
        
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
    
    clauses = re.split(r'\b(?:lekin|par|aur|but)\b|[,.]', text_lower)
    trigger_found = False
    
    for clause in clauses:
        tokens = re.findall(r'\w+', clause)
        
        has_body = any(fuzzy_match(tk, body_parts) for tk in tokens)
        has_pain = any(fuzzy_match(tk, pain_words) for tk in tokens)
        
        if has_body and has_pain:
            is_negated = any(neg in tokens for neg in negations)
            
            if has_severity:
                return GateResult("escalated", "clinical_urgent")
                
            if is_negated:
                continue
                
            trigger_found = True
            
    if trigger_found:
        if has_resolution and not has_active_marker:
            pass
        else:
            return GateResult("escalated", "clinical_urgent")
            
    # 3. Medical Advice
    if any(word in text_lower for word in ["dawai", "goli", "crocin", "kitni der", "dose"]):
        return GateResult("escalated", "medical_advice")
        
    return None
