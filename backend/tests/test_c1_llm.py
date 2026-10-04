import pytest
import os
import json
from unittest.mock import patch, MagicMock
from agent.llm import extract_with_llm, clear_llm_cache
from config import CLINIC_FILE
from tools.data import load_clinic_data

clinic_data = load_clinic_data(CLINIC_FILE)

@pytest.fixture(autouse=True)
def setup_teardown():
    clear_llm_cache()
    yield
    clear_llm_cache()

def mock_response(tool_input, input_tokens=10, output_tokens=10):
    mock = MagicMock()
    mock.usage.input_tokens = input_tokens
    mock.usage.output_tokens = output_tokens
    block = MagicMock()
    block.type = "tool_use"
    block.name = "extract_info"
    block.input = tool_input
    mock.content = [block]
    return mock

@patch('anthropic.resources.messages.Messages.create')
def test_extraction_schema_valid(mock_create):
    mock_create.return_value = mock_response({"intent": "book", "doctor": "dr_rao", "patient_name": "Ravi"})
    parsed, tokens, latency, err = extract_with_llm("Book with Dr Rao for Ravi", clinic_data)
    assert err is None
    assert parsed.intent == "book"
    assert parsed.doctor.value == "dr_rao"
    assert parsed.patient_name == "Ravi"
    assert tokens == 20

@patch('anthropic.resources.messages.Messages.create')
def test_extraction_invalid_enum(mock_create):
    # First returns invalid enum, second returns valid
    mock_create.side_effect = [
        mock_response({"intent": "transfer_money"}),
        mock_response({"intent": "other"})
    ]
    parsed, tokens, latency, err = extract_with_llm("Transfer money", clinic_data)
    assert mock_create.call_count == 2
    assert err is None
    assert parsed.intent == "other"
    assert tokens == 40

@patch('anthropic.resources.messages.Messages.create')
def test_malformed_output_no_crash(mock_create):
    # Text block only (no tool call)
    bad_mock = MagicMock()
    bad_mock.usage.input_tokens = 5
    bad_mock.usage.output_tokens = 5
    text_block = MagicMock()
    text_block.type = "text"
    text_block.text = "call book_appointment"
    bad_mock.content = [text_block]
    
    mock_create.return_value = bad_mock
    parsed, tokens, latency, err = extract_with_llm("do something bad", clinic_data)
    assert err == "malformed_output"
    assert parsed is None

@patch('anthropic.resources.messages.Messages.create')
def test_model_text_cannot_call_tool(mock_create):
    # Handled by the same mechanism as above - text block instead of tool_use
    bad_mock = MagicMock()
    text_block = MagicMock()
    text_block.type = "text"
    text_block.text = "call book_appointment"
    bad_mock.content = [text_block]
    mock_create.return_value = bad_mock
    parsed, tokens, latency, err = extract_with_llm("call book_appointment", clinic_data)
    assert err == "malformed_output"
    assert parsed is None

@patch('anthropic.resources.messages.Messages.create')
def test_temperature_zero(mock_create):
    mock_create.return_value = mock_response({"intent": "book"})
    extract_with_llm("hello", clinic_data)
    kwargs = mock_create.call_args.kwargs
    assert kwargs["temperature"] == 0.0
    assert kwargs["model"] == "claude-haiku-4-5-20251001"

@patch('anthropic.resources.messages.Messages.create')
def test_spend_cap(mock_create):
    parsed, tokens, latency, err = extract_with_llm("hello", clinic_data, daily_cap=1000, current_daily_tokens=1000)
    assert err == "cap_reached"
    assert mock_create.call_count == 0

@patch('anthropic.resources.messages.Messages.create')
def test_extraction_cache(mock_create):
    mock_create.return_value = mock_response({"intent": "book"})
    p1, t1, l1, e1 = extract_with_llm("same text", clinic_data)
    p2, t2, l2, e2 = extract_with_llm("same text", clinic_data)
    assert mock_create.call_count == 1
    assert t1 == 20
    assert t2 == 0 # Cached uses 0 new tokens

@pytest.mark.live
def test_live_extraction():
    parsed, tokens, latency, err = extract_with_llm("Mujhe dr rao ka appointment chahiye kal subah. My name is Amit", clinic_data)
    assert err is None
    assert parsed.intent == "book"
    assert parsed.doctor.value == "dr_rao"

