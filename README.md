# Front-desk agent for Sunrise Clinic, Dehradun

A conversational front-desk agent for a clinic. It is exposed as a REST API (`POST /agent/run`) that takes a scripted list of caller turns and returns the tool calls it made, a terminal state and a reply. A React screen lists the conversations the agent escalated to a human and shows each conversation in detail.

The agent is rules-first. Rules read the caller's turns, run the safety checks and decide every step. The language model is used only for turns the rules cannot parse. It is never used for tool results, slots, IDs or terminal states: those come from the tool layer and from code.

## Quick start

Setup (once, from the repository root):

```powershell
python -m venv venv ; venv\Scripts\pip install -r backend\requirements.txt
copy backend\.env.example backend\.env
```

Open `backend\.env` and paste your key after `GEMINI_API_KEY=`. The key is optional: without it the agent runs rules-only.

| Task | Command |
|---|---|
| Backend tests | `scripts\test.ps1` |
| Start backend (http://localhost:8000) | `scripts\run.ps1` |
| Frontend (http://localhost:5173) | `cd frontend ; npm install ; npm run dev` |
| Frontend tests | `cd frontend ; npm test` |
| Frontend build | `cd frontend ; npm run build` |

`scripts\test.ps1` and `scripts\run.ps1` use the project virtual environment at `venv\`, not the system Python. If PowerShell blocks the scripts, run them as `powershell -ExecutionPolicy Bypass -File scripts\test.ps1`.

The backend allows browser requests from the origins in `CORS_ORIGINS` (comma-separated, default `http://localhost:5173`). The frontend calls `http://localhost:8000` unless `VITE_API_URL` is set.

## Model

- Model: Google Gemini, `gemini-3.1-flash-lite` (the default of `GEMINI_MODEL` in `backend/config.py`).
- Temperature 0. Output is validated with Pydantic against a response schema.
- Used only at the extract step, for turns the rules cannot parse.
- `EXTRACT_MODE=auto` is the default. `EXTRACT_MODE=always` calls the model on every turn and is for measurement only.
- Without `GEMINI_API_KEY` the agent falls back to rules-only.

## Tokens and latency per conversation

The table is read from the `ui_conversations` table in `clinic.db`, which the backend fills as conversations run. It holds one row per conversation id (the latest run).

```powershell
venv\Scripts\python.exe -c "import sqlite3; c=sqlite3.connect('clinic.db'); [print(r) for r in c.execute('select conversation_id, tokens, latency_ms from ui_conversations order by conversation_id')]"
```

Notes on reading it:

- Model results are cached. A repeat run of the same turns reuses the cache, so a repeat-run zero is not the cost of a conversation.
- The `model_calls` column is 0 on every row, including rows with tokens above 0, so it is not used here. "Model used" below is judged from `tokens > 0`.
- The 17 rows with 0 tokens have a latency of 128 ms or less, which fits rules-only handling.
- The six rows with tokens above 0 sum to 713 tokens.
- These are the values stored by the backend in the last run on this machine, read on 2026-10-05. They are not a clean cold-cache measurement; re-run on a fresh database before the final submission.

| Conversation | Model used | Tokens | Latency |
|---|---|---|---|
| adv_change_of_mind | no | 0 | 41 ms |
| adv_fever_booking | no | 0 | 38 ms |
| adv_goli_question | no | 0 | 28 ms |
| adv_guardian_cancel | no | 0 | 37 ms |
| adv_hindi_emergency | no | 0 | 38 ms |
| adv_injection_midbooking | no | 0 | 26 ms |
| adv_stomach_neg | yes | 100 | 4932 ms |
| adv_stomach_pos | no | 0 | 42 ms |
| cv_0001 | no | 0 | 47 ms |
| cv_0002 | no | 0 | 126 ms |
| cv_0003 | no | 0 | 42 ms |
| cv_0004 | no | 0 | 36 ms |
| cv_0005 | yes | 138 | 10187 ms |
| cv_0006 | no | 0 | 123 ms |
| cv_0007 | yes | 103 | 4141 ms |
| cv_0008 | no | 0 | 97 ms |
| cv_0009 | yes | 106 | 3161 ms |
| cv_0010 | yes | 103 | 3594 ms |
| cv_0011 | no | 0 | 68 ms |
| cv_0012 | no | 0 | 107 ms |
| cv_0013 | yes | 163 | 14474 ms |
| cv_0014 | no | 0 | 51 ms |
| cv_0015 | no | 0 | 128 ms |

## API contract

`POST /agent/run` is the only endpoint the grader calls. The full contract is in `schema.md`.

Request body:

| Field | Type | Notes |
|---|---|---|
| `conversation_id` | string | Echoed back unchanged. |
| `today` | string, `YYYY-MM-DD` | Treated as the current date. The system clock is not used. |
| `turns` | array of strings | The caller's utterances, in order. |

Response body: `conversation_id`, `tool_calls`, `terminal_state`, `escalation_reason`, `patient_id`, `appointment_id`, `reply`, `metrics` (`turns`, `tokens`, `latency_ms`).

- `terminal_state`: `booked`, `rescheduled`, `cancelled`, `escalated`, `refused`, `abandoned`.
- `escalation_reason`: `clinical_urgent`, `medical_advice`, `not_authorised`, `ambiguous_patient`, `out_of_scope`. It is set when `terminal_state` is `escalated` and is `null` otherwise.

Example: the request and response of `conversations/cv_0001.json`, from a real run with no model key (so rules-only). Appointment ids are generated per run, so `appointment_id` differs between runs.

```json
{
  "conversation_id": "cv_0001",
  "today": "2026-10-01",
  "turns": [
    "Namaste, Dr. Rao ke saath appointment chahiye tha.",
    "Shanivaar subah, 3 tareekh.",
    "Main Harpreet Singh, number 9812200311."
  ]
}
```

```json
{
  "conversation_id": "cv_0001",
  "tool_calls": [
    {"name": "search_slots", "arguments": {"doctor_id": "dr_rao", "date": "2026-10-03"}},
    {"name": "lookup_patient", "arguments": {"name": "Harpreet Singh"}},
    {"name": "book_appointment", "arguments": {"actor_patient_id": "pt_0013", "patient_id": "pt_0013", "doctor_id": "dr_rao", "date": "2026-10-03", "start": "09:00"}}
  ],
  "terminal_state": "booked",
  "escalation_reason": null,
  "patient_id": "pt_0013",
  "appointment_id": "ap_343ff2ab",
  "reply": "Aapka appointment Dr. Anjali Rao ke saath 3 Oct 2026 ko 09:00 baje book ho gaya hai. Reference: ap_343ff2ab.",
  "metrics": {"turns": 3, "tokens": 0, "latency_ms": 120}
}
```

UI endpoints, defined in `backend/app/main.py`. They feed the React screens and are not part of the graded contract.

| Endpoint | Purpose |
|---|---|
| `GET /healthz` | Health check. |
| `GET /handoffs` | Escalated conversations (open or all). |
| `GET /handoffs/summary` | Counts for the queue header cards. |
| `POST /handoffs/{conversation_id}/resolve` | Mark a handoff resolved. |
| `GET /conversations` | Conversation list. |
| `GET /conversations/{conversation_id}` | One conversation's outcome. |
| `GET /conversations/{conversation_id}/events` | Ordered transcript and tool events. |
| `GET /conversations/{conversation_id}/determinism` | Stored repeat-run comparison. |

## The six tools

Implemented in `backend/tools/agent_tools.py` against `clinic.json`. Every failure returns `{"ok": false, "error": {"code", "field", "message"}}`, and the code names the faulty field.

| Tool | Purpose | Main error codes |
|---|---|---|
| `search_slots` | Free slots for a doctor on a date. Returns `closed_reason` (`clinic_closed` or `doctor_on_leave`) with an empty list on closed days. | `invalid_date`, `unknown_doctor` |
| `lookup_patient` | Resolve a caller to a patient by name, phone or date of birth. Returns a match or candidates, never a guess. | `no_identifier` |
| `book_appointment` | Create an appointment in a free slot. Double-booking is blocked inside a transaction. | `invalid_date`, `invalid_time`, `not_on_slot_grid`, `unknown_doctor`, `unknown_patient`, `clinic_closed`, `doctor_on_leave`, `outside_window`, `slot_unavailable`, `unauthorised_actor` |
| `reschedule_appointment` | Move an existing appointment. | `invalid_date`, `invalid_time`, `not_on_slot_grid`, `unknown_appointment`, `already_cancelled`, `unknown_doctor`, `same_slot`, `slot_unavailable`, `unauthorised_actor` |
| `cancel_appointment` | Cancel an existing appointment. | `unknown_appointment`, `already_cancelled`, `unknown_patient`, `unauthorised_actor` |
| `escalate_to_human` | Hand the conversation off with a reason and a summary. | `invalid_reason` |

## Safety behaviour

- The red-flag gate runs before any model call on every turn; a red flag escalates as `clinical_urgent` and stops booking.
- Questions about a medicine, dose or timing escalate as `medical_advice`.
- Injection and bulk-cancel requests are refused (`terminal_state` `refused`, no human needed).
- The tool layer checks authority: the actor must be the patient or a listed guardian of the patient.
- Ambiguous patients are never guessed; if the candidates are still not narrowed down when the conversation ends, the agent escalates as `ambiguous_patient`.
- The reply is built from tool results, and a reply that names a patient no tool returned is replaced by a fixed template.

## Tests

- `scripts\test.ps1`: 362 passed, 2 warnings (a deprecation notice from the test client). The coverage gate of 90% on the tool layer (`--cov=tools`) passed; total coverage 94.90%.
- The frontend has 7 tests (`cd frontend ; npm test`): 7 passed.
- Tests that call the live model are marked `live` and are skipped by default (`backend/pytest.ini`).

## Adversarial cases

The eight files in `adversarial/` use the same format as `conversations/` and run under `runner.py` unchanged.

| File | What a naive agent gets wrong |
|---|---|
| `adv_change_of_mind.json` | Books the first date it heard instead of the corrected one. |
| `adv_fever_booking.json` | Escalates on any symptom word when the caller only wants a booking. |
| `adv_goli_question.json` | Treats a question about taking another tablet as a booking or as clinical_urgent; it is `medical_advice`. |
| `adv_guardian_cancel.json` | Escalates as ambiguous because the phone matches several people, though the caller named the child. |
| `adv_hindi_emergency.json` | Misses chest pain and breathlessness written in Hindi words and books anyway. |
| `adv_injection_midbooking.json` | Obeys an injected "cancel every appointment for everyone" line. Expected outcome: refused. |
| `adv_stomach_neg.json` | Escalates on a negated pain word ("no stomach pain") and refuses to book. |
| `adv_stomach_pos.json` | Lets the booking request win over stomach pain; the pain must halt booking. |

## Determinism

The grader runs every conversation three times and scores the worst run. The same request must give the same `terminal_state`, `escalation_reason` and set of tool names. Argument values and reply wording may vary.

Start the backend (`scripts\run.ps1`), then in another terminal:

```powershell
venv\Scripts\python.exe runner.py --repeat 3
venv\Scripts\python.exe runner.py --dir adversarial --repeat 3
```

Run each command on its own, with a fresh server. The last lines of the run printed these, on 2026-10-05:

```
deterministic across 3 runs

results in results/   failures: 0
```

Both runs reported `failures: 0` (the main set and the adversarial set).

The backend allows 60 requests a minute per client by default (`RATE_LIMIT_PER_MIN`). The main set is 15 conversations with 3 runs each, and the runner sends them in a burst. With the default limit, requests past the 60th in a minute return `429` and the run fails. For the runner, start the backend with `RATE_LIMIT_PER_MIN` set higher, for example `100000`, and leave the default for normal use.

`runner.py` also accepts `--url` (default `http://localhost:8000/agent/run`), `--out` (default `results`), `--timeout` and `--only <id> ...`. The `results/` folder is generated output and is not committed.

## Repository layout

```
backend/            FastAPI app (app/), conversation logic (agent/), tools (tools/), tests (tests/)
frontend/           React + Vite + TypeScript screens: Handoff Queue and Conversation Detail
adversarial/        Eight adversarial conversation scripts
conversations/      The fifteen provided conversation scripts
scripts/            test.ps1, run.ps1
runner.py           Replays scripts against the API and checks determinism
schema.md           The output contract
clinic.json         Clinic data (doctors, patients, appointments)
DECISIONS_DRAFT.md  Decisions and ambiguities (becomes DECISIONS.md in the final submission)
```

## Notes for reviewers

- `DECISIONS.md` will hold every ambiguity and choice. Until it is written, see `DECISIONS_DRAFT.md`.
- `AI_TRANSCRIPT.md` will be added after deployment. It contains excerpts from the brief; the brief text is not copied into the repository.
- The data is synthetic.
