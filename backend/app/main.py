from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel, Field, field_validator
from typing import List, Optional, Any
import time
import logging
from datetime import datetime

from agent.machine import AgentMachine
from config import CLINIC_FILE, DB_PATH, RATE_LIMIT_PER_MIN

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI()

class AgentRequest(BaseModel):
    conversation_id: str
    today: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    turns: List[str] = Field(min_length=1, max_length=50)

    @field_validator('today')
    @classmethod
    def validate_today_calendar(cls, v: str) -> str:
        try:
            datetime.strptime(v, "%Y-%m-%d")
        except ValueError:
            raise ValueError("Invalid calendar date")
        return v

class ToolCall(BaseModel):
    name: str
    arguments: dict
    result: Optional[dict] = None

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

ip_tracking = {}

@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    if request.url.path == "/agent/run":
        ip = request.client.host if request.client else "127.0.0.1"
        now = time.time()
        if ip not in ip_tracking:
            ip_tracking[ip] = []
        ip_tracking[ip] = [t for t in ip_tracking[ip] if now - t < 60]
        if len(ip_tracking[ip]) >= RATE_LIMIT_PER_MIN:
            return JSONResponse(status_code=429, content={"detail": "Rate limit exceeded"})
        ip_tracking[ip].append(now)
    return await call_next(request)

@app.get("/healthz")
def healthz():
    return {"status": "ok"}

@app.post("/agent/run", response_model=AgentResponse)
def run_agent(req: AgentRequest):
    try:
        machine = AgentMachine(CLINIC_FILE, DB_PATH, req.today)
        turns = req.turns
        for i, turn in enumerate(turns):
            machine.is_last_turn = (i == len(turns) - 1)
            machine.process_turn(turn)
            
        res = machine.finalize()
        machine.conn.close()
        
        # Observability: Request logging
        m = res.get("metrics", {})
        tokens = m.get("tokens", 0)
        latency = m.get("latency_ms", 0)
        term_state = res.get("terminal_state", "abandoned")
        esc_reason = res.get("escalation_reason")
        num_tools = len(res.get("tool_calls", []))
        logger.info(f"conversation_id={req.conversation_id} terminal_state={term_state} escalation_reason={esc_reason} tool_calls={num_tools} tokens={tokens} latency_ms={latency}")

        
        return AgentResponse(
            conversation_id=req.conversation_id,
            tool_calls=res.get("tool_calls", []),
            terminal_state=res.get("terminal_state", "abandoned"),
            escalation_reason=res.get("escalation_reason"),
            patient_id=res.get("patient_id"),
            appointment_id=res.get("appointment_id"),
            reply=res.get("reply", ""),
            metrics=Metrics(**res.get("metrics", {"turns": len(turns), "tokens": 0, "latency_ms": 0}))
        )
    except Exception as e:
        logger.error(f"Error inside turn loop: {e}", exc_info=True)
        return JSONResponse(
            status_code=200,
            content={
                "conversation_id": req.conversation_id,
                "tool_calls": [],
                "terminal_state": "escalated",
                "escalation_reason": "out_of_scope",
                "patient_id": None,
                "appointment_id": None,
                "reply": "An internal error occurred. A human is connecting.",
                "metrics": {"turns": len(req.turns), "tokens": 0, "latency_ms": 0}
            }
        )
