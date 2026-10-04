import os
import json
import hashlib
import time
from typing import Optional, Literal, Dict, Any, Tuple
from enum import Enum
from pydantic import BaseModel, ValidationError, create_model
import anthropic

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

def extract_with_llm(
    text: str, 
    clinic_data, 
    daily_cap: int = 100000, 
    current_daily_tokens: int = 0
) -> Tuple[Optional[BaseModel], int, float, Optional[str]]:
    if current_daily_tokens >= daily_cap:
        return None, 0, 0.0, "cap_reached"
        
    text_hash = hashlib.sha256(text.encode('utf-8')).hexdigest()
    if text_hash in _CACHE:
        cached = _CACHE[text_hash]
        return cached["model"], 0, 0.0, cached["error"]

    ExtractionModel = get_extraction_model(clinic_data)
    schema = ExtractionModel.model_json_schema()
    
    api_key = os.environ.get("ANTHROPIC_API_KEY", "dummy")
    client = anthropic.Anthropic(api_key=api_key, max_retries=0)
    
    system_prompt = "Extract appointment details from the user's turn. Output ONLY JSON matching the schema."
    
    tools = [{
        "name": "extract_info",
        "description": "Extract structured information.",
        "input_schema": schema
    }]

    def call_api(error_feedback: str = ""):
        prompt = text
        if error_feedback:
            prompt += f"\n\nPrevious attempt failed with validation error: {error_feedback}. Please fix and return correct JSON."
            
        start = time.time()
        try:
            response = client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=1024,
                temperature=0.0,
                system=system_prompt,
                tools=tools,
                tool_choice={"type": "tool", "name": "extract_info"},
                messages=[{"role": "user", "content": prompt}],
                timeout=10.0
            )
            latency = time.time() - start
            tokens = response.usage.input_tokens + response.usage.output_tokens
            
            for block in response.content:
                if block.type == 'tool_use' and block.name == 'extract_info':
                    return block.input, tokens, latency
            return None, tokens, latency
        except Exception as e:
            return None, 0, time.time() - start

    raw_input, tokens, latency = call_api()
    if raw_input is None:
        _CACHE[text_hash] = {"model": None, "error": "malformed_output"}
        return None, tokens, latency, "malformed_output"
        
    try:
        parsed = ExtractionModel.model_validate(raw_input)
        _CACHE[text_hash] = {"model": parsed, "error": None}
        return parsed, tokens, latency, None
    except ValidationError as e:
        raw_input_2, tokens_2, latency_2 = call_api(error_feedback=str(e))
        tot_tokens = tokens + tokens_2
        tot_latency = latency + latency_2
        
        if raw_input_2 is None:
            _CACHE[text_hash] = {"model": None, "error": "malformed_output"}
            return None, tot_tokens, tot_latency, "malformed_output"
            
        try:
            parsed_2 = ExtractionModel.model_validate(raw_input_2)
            _CACHE[text_hash] = {"model": parsed_2, "error": None}
            return parsed_2, tot_tokens, tot_latency, None
        except ValidationError:
            _CACHE[text_hash] = {"model": None, "error": "validation_failed"}
            return None, tot_tokens, tot_latency, "validation_failed"

