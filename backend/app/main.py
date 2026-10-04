from fastapi import FastAPI
from pydantic import BaseModel
from typing import List, Optional, Any

app = FastAPI()

class AgentRequest(BaseModel):
    conversation_id: str
    today: str
    turns: List[str]

class ToolCall(BaseModel):
    name: str
    arguments: dict

class Metrics(BaseModel):
    turns: int
    tokens: int
    latency_ms: int

class AgentResponse(BaseModel):
    conversation_id: str
    tool_calls: List[ToolCall]
    terminal_state: str
    escalation_reason: Optional[str] = None
    patient_id: Optional[str] = None
    appointment_id: Optional[str] = None
    reply: str
    metrics: Metrics

@app.post("/agent/run", response_model=AgentResponse)
def run_agent(req: AgentRequest):
    return AgentResponse(
        conversation_id=req.conversation_id,
        tool_calls=[],
        terminal_state="abandoned",
        escalation_reason=None,
        patient_id=None,
        appointment_id=None,
        reply="Stub reply.",
        metrics=Metrics(turns=len(req.turns), tokens=0, latency_ms=10)
    )

