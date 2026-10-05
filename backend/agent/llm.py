import os
import json
import hashlib
import time
from typing import Optional, Literal, Dict, Any, Tuple
from enum import Enum
from pydantic import BaseModel, ValidationError, create_model
import logging

from config import GEMINI_MODEL

logger = logging.getLogger(__name__)

class IntentEnum(str, Enum):
    book = "book"
    reschedule = "reschedule"
    cancel = "cancel"
    other = "other"

class BaseExtraction(BaseModel):
    intent: IntentEnum
    date_phrase: Optional[str] = None
    time_phrase: Optional[str] = None
    patient_name: Optional[str] = None
    phone: Optional[str] = None
    dob: Optional[str] = None
    on_behalf_of: Optional[str] = None

def get_extraction_model(clinic_data):
    doc_dict = {k: k for k in clinic_data.doctors.keys()}
    DoctorEnum = Enum("DoctorEnum", doc_dict)
    return create_model(
        "ExtractionResult",
        doctor=(Optional[DoctorEnum], None),
        __base__=BaseExtraction
    )

_CACHE: Dict[str, Dict[str, Any]] = {}

def clear_llm_cache():
    _CACHE.clear()


def _remember(text_hash: str, model, error, tokens: int, latency: float) -> None:
    """Cache an answer together with what it cost the first time."""
    _CACHE[text_hash] = {"model": model, "error": error, "tokens": tokens, "latency": latency}


def cold_usage(text: str) -> Tuple[int, float]:
    """(tokens, seconds) the first, uncached call for this turn text cost. (0, 0.0) if unknown.

    A repeat run reuses the cached answer and costs nothing, but the cost of the conversation is what
    the first run paid. The UI and README report that cold cost, not the zero of a cache hit.
    """
    entry = _CACHE.get(hashlib.sha256(text.encode("utf-8")).hexdigest())
    if not entry:
        return 0, 0.0
    return int(entry.get("tokens", 0)), float(entry.get("latency", 0.0))

def extract_with_llm(
    text: str, 
    clinic_data, 
    daily_cap: int = 100000, 
    current_daily_tokens: int = 0,
    usage_sink: Optional[list] = None
) -> Tuple[Optional[BaseModel], int, float, Optional[str]]:
    if current_daily_tokens >= daily_cap:
        logger.info(f"provider=gemini model={GEMINI_MODEL} outcome=skipped_cap tokens=0 latency_ms=0")
        return None, 0, 0.0, "cap_reached"
        
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        logger.info(f"provider=gemini model={GEMINI_MODEL} outcome=skipped_no_key tokens=0 latency_ms=0")
        return None, 0, 0.0, "no_key"

    text_hash = hashlib.sha256(text.encode('utf-8')).hexdigest()
    if text_hash in _CACHE:
        cached = _CACHE[text_hash]
        return cached["model"], 0, 0.0, cached["error"]

    ExtractionModel = get_extraction_model(clinic_data)
    
    from google import genai
    from google.genai import types
    client = genai.Client(api_key=api_key)
    
    system_prompt = "Extract appointment details from the user's turn. Output ONLY JSON matching the schema."

    def call_api(error_feedback: str = ""):
        prompt = text
        if error_feedback:
            prompt += f"\n\nPrevious attempt failed with validation error: {error_feedback}. Please fix and return correct JSON."
            
        start = time.time()
        try:
            response = client.models.generate_content(
                model=GEMINI_MODEL,
                contents=prompt,
                config=types.GenerateContentConfig(
                    temperature=0.0,
                    response_mime_type="application/json",
                    response_schema=ExtractionModel,
                    system_instruction=system_prompt
                )
            )
            latency = time.time() - start
            usage = response.usage_metadata
            tokens = 0
            if usage:
                # Provider-reported total (includes any thinking tokens) when available, else prompt + candidates.
                total = getattr(usage, "total_token_count", None)
                prompt_t, cand_t = usage.prompt_token_count, usage.candidates_token_count
                tokens = total if isinstance(total, int) else (prompt_t + cand_t)
                if usage_sink is not None:
                    usage_sink.append({"outcome": "ok", "prompt": prompt_t, "candidates": cand_t, "total": tokens})
            elif usage_sink is not None:
                usage_sink.append({"outcome": "ok", "prompt": 0, "candidates": 0, "total": 0})
            
            return response.text, tokens, latency, None
        except Exception as e:
            err_str = str(e)
            outcome = "rate_limited" if ("429" in err_str or "RESOURCE_EXHAUSTED" in err_str) else "error"
            if usage_sink is not None:
                usage_sink.append({"outcome": outcome, "prompt": 0, "candidates": 0, "total": 0})
            return None, 0, time.time() - start, outcome

    raw_input, tokens, latency, err = call_api()
    if err:
        _remember(text_hash, None, err, tokens, latency)
        logger.info(f"provider=gemini model={GEMINI_MODEL} outcome={err} tokens={tokens} latency_ms={int(latency*1000)}")
        return None, tokens, latency, err
        
    try:
        parsed = ExtractionModel.model_validate_json(raw_input)
        _remember(text_hash, parsed, None, tokens, latency)
        logger.info(f"provider=gemini model={GEMINI_MODEL} outcome=ok tokens={tokens} latency_ms={int(latency*1000)}")
        return parsed, tokens, latency, None
    except ValidationError as e:
        logger.info(f"provider=gemini model={GEMINI_MODEL} outcome=invalid tokens={tokens} latency_ms={int(latency*1000)}")
        raw_input_2, tokens_2, latency_2, err_2 = call_api(error_feedback=str(e))
        tot_tokens = tokens + tokens_2
        tot_latency = latency + latency_2
        
        if err_2:
            _remember(text_hash, None, err_2, tot_tokens, tot_latency)
            logger.info(f"provider=gemini model={GEMINI_MODEL} outcome={err_2} tokens={tokens_2} latency_ms={int(latency_2*1000)}")
            return None, tot_tokens, tot_latency, err_2
            
        try:
            parsed_2 = ExtractionModel.model_validate_json(raw_input_2)
            _remember(text_hash, parsed_2, None, tot_tokens, tot_latency)
            logger.info(f"provider=gemini model={GEMINI_MODEL} outcome=ok tokens={tokens_2} latency_ms={int(latency_2*1000)}")
            return parsed_2, tot_tokens, tot_latency, None
        except ValidationError:
            _remember(text_hash, None, "invalid", tot_tokens, tot_latency)
            logger.info(f"provider=gemini model={GEMINI_MODEL} outcome=invalid tokens={tokens_2} latency_ms={int(latency_2*1000)}")
            return None, tot_tokens, tot_latency, "invalid"

