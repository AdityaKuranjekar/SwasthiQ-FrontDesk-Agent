import pytest
import json
import re
from agent.machine import AgentMachine
import glob

def test_no_invented_facts_in_summary():
    scripts = glob.glob('conversations/*.json') + glob.glob('adversarial/*.json')
    for script_file in scripts:
        with open(script_file) as f:
            script = json.load(f)
        
        tm = AgentMachine('clinic.json', 'test_summary.db', script.get('today', '2026-10-01'))
        caller_words = set()
        for i, turn in enumerate(script['turns']):
            words = re.findall(r'\b\w+\b', turn.lower())
            caller_words.update(words)
            tm.is_last_turn = (i == len(script['turns']) - 1)
            tm.process_turn(turn)
        
        tres = tm.finalize()
        tm.conn.close()
        
        if tres.get('terminal_state') == 'escalated':
            escalate_call = next((t for t in tres['tool_calls'] if t['name'] == 'escalate_to_human'), None)
            if escalate_call:
                summary = escalate_call['arguments']['summary']
                summary_words = re.findall(r'\b\w+\b', summary.lower())
                
                with open('clinic.json') as f:
                    clinic = json.load(f)
                names = set()
                for p in clinic['patients']:
                    names.update(re.findall(r'\b\w+\b', p['name'].lower()))
                for d in clinic['doctors']:
                    names.update(re.findall(r'\b\w+\b', d['name'].lower()))
                
                for w in summary_words:
                    assert w in caller_words or w in names or w.isdigit() or w in {'chest', 'severe', 'stomach', 'pain', 'breathlessness', 'dose', 'it', 'and', 'abandoned', 'to', 'down', 'the', 'made', 'appointment', 'kal', 'neither', 'timing', 'they', 'requested', 'no', 'multiple', 'caller', 'asks', 'guardian', 'patient', 'narrow', 'change', 'not', 'for', 'while', 'asked', 'be', 'medicine', 'booking', 'records', 'did', 'reports', 'listed', 'is', 'was', 'about', 'or', 'could', 'a', 'record', 'cancel', 'nor'}, f'Word "{w}" in summary "{summary}" not allowed'
