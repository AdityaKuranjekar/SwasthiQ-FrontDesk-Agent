import pytest
import os
import json
from unittest.mock import patch, MagicMock
from agent.llm import extract_with_llm, clear_llm_cache
from config import CLINIC_FILE
from tools.data import load_clinic_data

clinic_data = load_clinic_data(CLINIC_FILE)

@pytest.fixture(autouse=True)
def setup_teardown(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "dummy_key")
    clear_llm_cache()
    yield
    clear_llm_cache()

def mock_response(json_data, input_tokens=10, output_tokens=10):
    mock = MagicMock()
    mock.usage_metadata.prompt_token_count = input_tokens
    mock.usage_metadata.candidates_token_count = output_tokens
    mock.text = json.dumps(json_data)
    return mock

@patch('google.genai.models.Models.generate_content')
def test_extraction_schema_valid(mock_create):
    mock_create.return_value = mock_response({"intent": "book", "doctor": "dr_rao", "patient_name": "Ravi"})
    parsed, tokens, latency, err = extract_with_llm("Book with Dr Rao for Ravi", clinic_data)
    assert err is None
    assert parsed.intent == "book"
    assert parsed.doctor.value == "dr_rao"
    assert parsed.patient_name == "Ravi"
    assert tokens == 20

@patch('google.genai.models.Models.generate_content')
def test_extraction_invalid_enum(mock_create):
    mock_create.side_effect = [
        mock_response({"intent": "transfer_money"}),
        mock_response({"intent": "other"})
    ]
    parsed, tokens, latency, err = extract_with_llm("Transfer money", clinic_data)
    assert mock_create.call_count == 2
    assert err is None
    assert parsed.intent == "other"
    assert tokens == 40

@patch('google.genai.models.Models.generate_content')
def test_malformed_output_no_crash(mock_create):
    bad_mock = MagicMock()
    bad_mock.usage_metadata.prompt_token_count = 5
    bad_mock.usage_metadata.candidates_token_count = 5
    bad_mock.text = "this is not json"
    mock_create.return_value = bad_mock
    
    parsed, tokens, latency, err = extract_with_llm("do something bad", clinic_data)
    assert err == "invalid"
    assert parsed is None

@patch('google.genai.models.Models.generate_content')
def test_temperature_zero(mock_create):
    mock_create.return_value = mock_response({"intent": "book"})
    extract_with_llm("hello", clinic_data)
    kwargs = mock_create.call_args.kwargs
    assert kwargs["config"].temperature == 0.0

@patch('google.genai.models.Models.generate_content')
def test_spend_cap(mock_create):
    parsed, tokens, latency, err = extract_with_llm("hello", clinic_data, daily_cap=1000, current_daily_tokens=1000)
    assert err == "cap_reached"
    assert mock_create.call_count == 0

@patch('google.genai.models.Models.generate_content')
def test_extraction_cache(mock_create):
    mock_create.return_value = mock_response({"intent": "book"})
    p1, t1, l1, e1 = extract_with_llm("same text", clinic_data)
    p2, t2, l2, e2 = extract_with_llm("same text", clinic_data)
    assert mock_create.call_count == 1
    assert t1 == 20
    assert t2 == 0 

@patch('google.genai.models.Models.generate_content')
def test_no_key_skips_network(mock_create, monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    parsed, tokens, latency, err = extract_with_llm("hello", clinic_data)
    assert err == "no_key"
    assert parsed is None
    assert mock_create.call_count == 0

@patch('google.genai.models.Models.generate_content')
def test_llm_rate_limited(mock_create):
    mock_create.side_effect = Exception("429 RESOURCE_EXHAUSTED Quota exceeded")
    parsed, tokens, latency, err = extract_with_llm("hello", clinic_data)
    assert err == "rate_limited"
    assert parsed is None
    assert tokens == 0

@patch('google.genai.models.Models.generate_content')
def test_llm_network_error(mock_create):
    mock_create.side_effect = Exception("Connection reset by peer")
    parsed, tokens, latency, err = extract_with_llm("hello", clinic_data)
    assert err == "error"
    assert parsed is None
    assert tokens == 0

from agent.machine import AgentMachine
@patch("agent.llm.extract_with_llm")
def test_extract_mode_always_calls_model(mock_extract, monkeypatch):
    monkeypatch.setattr("config.EXTRACT_MODE", "always")
    mock_extract.return_value = (None, 10, 0.1, "no_key")
    
    machine = AgentMachine(CLINIC_FILE, ":memory:", "2026-10-04")
    machine.process_turn("hello world")
    machine.process_turn("second turn")
    
    assert mock_extract.call_count == 2
