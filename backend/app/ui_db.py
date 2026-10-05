import sqlite3


def init_ui_db(db_path: str):
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    c.executescript("""
        CREATE TABLE IF NOT EXISTS ui_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            conversation_id TEXT,
            event_type TEXT,
            position INTEGER,
            timestamp TEXT,
            content TEXT
        );
        CREATE TABLE IF NOT EXISTS ui_handoffs (
            conversation_id TEXT PRIMARY KEY,
            caller_said TEXT,
            escalation_reason TEXT,
            created_at TEXT,
            resolved INTEGER DEFAULT 0,
            resolved_by TEXT,
            resolved_at TEXT,
            note TEXT
        );
        CREATE TABLE IF NOT EXISTS ui_conversations (
            conversation_id TEXT PRIMARY KEY,
            date TEXT,
            time TEXT,
            created_at TEXT,
            intent TEXT,
            terminal_state TEXT,
            escalation_reason TEXT,
            patient_id TEXT,
            appointment_id TEXT,
            tool_call_count INTEGER,
            turns INTEGER,
            tokens INTEGER,
            latency_ms INTEGER,
            model_calls INTEGER,
            usage_json TEXT
        );
        CREATE TABLE IF NOT EXISTS ui_determinism (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            conversation_id TEXT,
            run_index INTEGER,
            terminal_state TEXT,
            escalation_reason TEXT,
            tool_calls TEXT
        );
    """)
    # Databases created by earlier stages: add any missing columns.
    have = {r[1] for r in c.execute("PRAGMA table_info(ui_conversations)")}
    for col, typ in (("created_at", "TEXT"), ("intent", "TEXT"), ("model_calls", "INTEGER"), ("usage_json", "TEXT")):
        if col not in have:
            c.execute(f"ALTER TABLE ui_conversations ADD COLUMN {col} {typ}")
    conn.commit()
    conn.close()
