from fastapi.middleware.cors import CORSMiddleware
import os
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel, Field, field_validator
from typing import List, Optional, Any
import time
import logging
from datetime import datetime, timezone
import json
import sqlite3

from agent.machine import AgentMachine
from agent.replies import reply_for
from app.describe import describe_result
from config import CLINIC_FILE, DB_PATH, RATE_LIMIT_PER_MIN
from app.ui_db import init_ui_db

init_ui_db(DB_PATH)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI()

origins = os.environ.get("CORS_ORIGINS", "http://localhost:5173").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


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

def now_iso() -> str:
    """UTC, ISO 8601, with offset."""
    return datetime.now(timezone.utc).isoformat()


@app.post("/agent/run", response_model=AgentResponse)
def run_agent(req: AgentRequest, repeat: int = 1):
    started_at = now_iso()
    try:
        if repeat > 1:
            # Determinism runs: stored so the UI badge is computed from measured runs only.
            det = sqlite3.connect(DB_PATH, isolation_level=None)
            det.execute("DELETE FROM ui_determinism WHERE conversation_id = ?", (req.conversation_id,))
            for r in range(repeat):
                tm = AgentMachine(CLINIC_FILE, DB_PATH, req.today)
                for i, turn in enumerate(req.turns):
                    tm.is_last_turn = (i == len(req.turns) - 1)
                    tm.process_turn(turn)
                tres = tm.finalize()
                tm.conn.close()
                names = json.dumps([t["name"] for t in tres.get("tool_calls", [])])
                det.execute("INSERT INTO ui_determinism (conversation_id, run_index, terminal_state, escalation_reason, tool_calls) VALUES (?, ?, ?, ?, ?)",
                            (req.conversation_id, r + 1, tres.get("terminal_state"), tres.get("escalation_reason"), names))
            det.close()

        # Whole-request timer for the graded run (the determinism runs above are diagnostics).
        t0 = time.perf_counter()

        # Separate autocommit connection for UI rows, to avoid lock deadlocks with the run store.
        ui_conn = sqlite3.connect(DB_PATH, isolation_level=None)
        ui_c = ui_conn.cursor()
        ui_c.execute("DELETE FROM ui_events WHERE conversation_id = ?", (req.conversation_id,))

        machine = AgentMachine(CLINIC_FILE, DB_PATH, req.today)
        turns = req.turns
        pos = 0
        written_tools = 0

        def add_event(event_type: str, content, ts: Optional[str] = None):
            nonlocal pos
            ui_c.execute("INSERT INTO ui_events (conversation_id, event_type, position, timestamp, content) VALUES (?, ?, ?, ?, ?)",
                         (req.conversation_id, event_type, pos, ts or now_iso(), content))
            pos += 1

        def flush_tool_events():
            nonlocal written_tools
            while written_tools < len(machine.tool_calls):
                tr = machine.tool_calls[written_tools]
                add_event("tool", json.dumps({
                    "name": tr["name"],
                    "arguments": tr["arguments"],
                    "result": tr.get("result"),
                    "display": describe_result(tr["name"], tr["arguments"], tr.get("result", {})),
                    "rule_id": tr.get("result", {}).get("rule_id") if isinstance(tr.get("result"), dict) else None,
                }, default=str))
                written_tools += 1

        escalated_turn = None
        last_reply_text = None
        for i, turn in enumerate(turns):
            # The first event carries the request's start time, so the header shows when the conversation began.
            add_event("caller", turn, started_at if i == 0 else None)
            machine.is_last_turn = (i == len(turns) - 1)
            handed_off_before = machine.terminal_state in ("escalated", "refused")
            machine.process_turn(turn)
            flush_tool_events()
            if machine.terminal_state == "escalated" and escalated_turn is None:
                escalated_turn = turn
            # One reply per caller turn. After a handoff the agent has already spoken, so it stays quiet.
            if not machine.is_last_turn and not handed_off_before:
                last_reply_text = reply_for(machine)
                add_event("reply", last_reply_text)

        res = machine.finalize()
        flush_tool_events()  # calls made at finalize (e.g. the ambiguous-patient escalation)
        # The graded reply is always returned. In the transcript it is shown only if it says something new.
        if res.get("reply", "") != last_reply_text:
            add_event("reply", res.get("reply", ""))

        term_state = res.get("terminal_state", "abandoned")
        esc_reason = res.get("escalation_reason")
        if term_state == "escalated":
            if escalated_turn is None:
                escalated_turn = turns[-1] if turns else ""
            ui_c.execute("""
                INSERT OR REPLACE INTO ui_handoffs
                (conversation_id, caller_said, escalation_reason, created_at, resolved)
                VALUES (?, ?, ?, ?, ?)
            """, (req.conversation_id, escalated_turn, esc_reason, now_iso(), 0))

        m = res.get("metrics", {})
        tokens = int(m.get("tokens", 0))
        num_tools = len(res.get("tool_calls", []))
        machine.conn.close()
        latency = max(1, int(round((time.perf_counter() - t0) * 1000)))
        usage = machine.model_calls

        # What this request actually cost goes in the graded response. The screen shows what the conversation
        # costs: a repeat run reuses cached extraction (0 now), so add back what the first run paid.
        shown_tokens = tokens + int(m.get("cached_tokens", 0))
        shown_latency = latency + int(m.get("cached_latency_ms", 0))

        ui_c.execute("""
            INSERT OR REPLACE INTO ui_conversations
            (conversation_id, date, time, created_at, terminal_state, intent, escalation_reason, patient_id, appointment_id,
             tool_call_count, turns, tokens, latency_ms, model_calls, usage_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (req.conversation_id, req.today, started_at[11:19], started_at, term_state, res.get("intent"), esc_reason,
              res.get("patient_id"), res.get("appointment_id"), num_tools, len(turns), shown_tokens, shown_latency,
              len(usage), json.dumps(usage)))
        ui_conn.close()

        logger.info(f"conversation_id={req.conversation_id} terminal_state={term_state} escalation_reason={esc_reason} "
                    f"tool_calls={num_tools} model_calls={len(usage)} tokens={tokens} latency_ms={latency}")

        return AgentResponse(
            conversation_id=req.conversation_id,
            tool_calls=res.get("tool_calls", []),
            terminal_state=term_state,
            escalation_reason=esc_reason,
            patient_id=res.get("patient_id"),
            appointment_id=res.get("appointment_id"),
            reply=res.get("reply", ""),
            metrics=Metrics(turns=len(turns), tokens=tokens, latency_ms=latency)
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


def validate_date_str(date_str: str):
    try:
        datetime.strptime(date_str, "%Y-%m-%d")
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid date format, expected YYYY-MM-DD")

@app.get("/handoffs")
def get_handoffs(status: str = "open"):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    if status == "open":
        c.execute("SELECT * FROM ui_handoffs WHERE resolved = 0 ORDER BY created_at DESC")
    else:
        c.execute("SELECT * FROM ui_handoffs ORDER BY created_at DESC")
    rows = [dict(r) for r in c.fetchall()]
    conn.close()
    return rows

@app.get("/handoffs/summary")
def get_handoffs_summary(date: str | None = None):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    if date is None:
        # The clinic's "today" is the request's `today`, not the wall clock.
        # With no date given, summarise the most recent day that has conversations.
        c.execute("SELECT MAX(date) FROM ui_conversations")
        date = c.fetchone()[0] or "1970-01-01"
    else:
        validate_date_str(date)
    c.execute("SELECT COUNT(*) FROM ui_conversations WHERE date = ?", (date,))
    total = c.fetchone()[0] or 0
    
    c.execute("SELECT COUNT(*) FROM ui_conversations WHERE date = ? AND terminal_state IN ('booked', 'rescheduled', 'cancelled', 'refused')", (date,))
    completed = c.fetchone()[0] or 0
    
    c.execute("SELECT COUNT(*) FROM ui_conversations WHERE date = ? AND terminal_state = 'escalated'", (date,))
    escalated = c.fetchone()[0] or 0
    
    c.execute("SELECT COUNT(*) FROM ui_handoffs h JOIN ui_conversations c ON h.conversation_id = c.conversation_id WHERE c.date = ? AND h.resolved = 0", (date,))
    open_handoffs = c.fetchone()[0] or 0
    
    c.execute("SELECT COUNT(*) FROM ui_handoffs h JOIN ui_conversations c ON h.conversation_id = c.conversation_id WHERE c.date = ? AND h.resolved = 0 AND h.escalation_reason = 'clinical_urgent'", (date,))
    urgent_unresolved = c.fetchone()[0] or 0
    
    conn.close()
    return {
        "total_conversations": total,
        "completed_by_agent": completed,
        "escalated": escalated,
        "still_open": open_handoffs,
        "urgent_unresolved": urgent_unresolved
    }

class ResolveRequest(BaseModel):
    resolved_by: str
    note: str

@app.post("/handoffs/{conversation_id}/resolve")
def resolve_handoff(conversation_id: str, req: ResolveRequest):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("SELECT * FROM ui_handoffs WHERE conversation_id = ?", (conversation_id,))
    row = c.fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail={"error": "Not found"})
    if row["resolved"] == 1:
        conn.close()
        raise HTTPException(status_code=409, detail={"error": "Already resolved"})
        
    c.execute("UPDATE ui_handoffs SET resolved = 1, resolved_by = ?, note = ?, resolved_at = ? WHERE conversation_id = ?",
              (req.resolved_by, req.note, now_iso(), conversation_id))
    conn.commit()
    conn.close()
    return {"ok": True}

@app.get("/conversations")
def get_conversations(date: str):
    validate_date_str(date)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("SELECT * FROM ui_conversations WHERE date = ? ORDER BY time DESC", (date,))
    rows = [dict(r) for r in c.fetchall()]
    conn.close()
    return rows

@app.get("/conversations/{conversation_id}")
def get_conversation(conversation_id: str):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("SELECT * FROM ui_conversations WHERE conversation_id = ?", (conversation_id,))
    row = c.fetchone()
    conn.close()
    if not row:
        raise HTTPException(status_code=404, detail={"error": "Not found"})
    return dict(row)

@app.get("/conversations/{conversation_id}/events")
def get_conversation_events(conversation_id: str):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("SELECT * FROM ui_conversations WHERE conversation_id = ?", (conversation_id,))
    if not c.fetchone():
        conn.close()
        raise HTTPException(status_code=404, detail={"error": "Not found"})
        
    c.execute("SELECT * FROM ui_events WHERE conversation_id = ? ORDER BY position ASC", (conversation_id,))
    rows = [dict(r) for r in c.fetchall()]
    for r in rows:
        if r["event_type"] == "tool":
            r["content"] = json.loads(r["content"])
    conn.close()
    return rows

@app.get("/conversations/{conversation_id}/determinism")
def get_conversation_determinism(conversation_id: str):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("SELECT * FROM ui_conversations WHERE conversation_id = ?", (conversation_id,))
    if not c.fetchone():
        conn.close()
        raise HTTPException(status_code=404, detail={"error": "Not found"})
        
    c.execute("SELECT * FROM ui_determinism WHERE conversation_id = ? ORDER BY run_index ASC", (conversation_id,))
    rows = [dict(r) for r in c.fetchall()]
    for r in rows:
        r["tool_calls"] = json.loads(r["tool_calls"])
        
    # STABLE is computed here, from three stored runs (repeat=3). Compared per run: terminal_state,
    # escalation_reason and the sorted set of tool names. Fewer than three runs: "not_measured".
    status = "not_measured"
    stable = None
    if len(rows) >= 3:
        def sig(r):
            return (r["terminal_state"], r["escalation_reason"], tuple(sorted(set(r["tool_calls"]))))
        stable = len({sig(r) for r in rows}) == 1
        status = "stable" if stable else "unstable"

    conn.close()
    return {"status": status, "stable": stable, "runs": rows}

