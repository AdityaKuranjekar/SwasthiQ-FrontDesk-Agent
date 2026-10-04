# PLAN.md: Clinic Front Desk Agent, build plan (Phases A to C, Stages 0 to 5)

Hand-off plan for building the backend core. Decisions come from `DECISIONS_DRAFT.md`, Rounds 8 and 10. Read those first. Frontend, adversarial cases and deployment are later phases, not in this plan.

## Ground rules (apply to every phase)

1. **No `datetime.now()` or `date.today()` anywhere in the agent.** Every date resolves against `today` from the request.
2. **The tool layer never imports or calls an LLM.** Enforce with a test that greps the tool package for model SDK imports.
3. **The model is called only at the `EXTRACT` state** (Phase C). It never chooses tools, IDs, slots or terminal states.
4. **Each run loads `clinic.json` fresh.** No state leaks between runs. Enforce with a test.
5. **Every phase ends with its gate.** Do not start the next phase until the gate is green.
6. **Keep `DECISIONS_DRAFT.md` updated** with any new ambiguity you hit, tagged `[UNCLEAR]` or `[CHOICE]`.
7. **Python 3.11** target, compatible with 3.9 syntax where feasible. `runner.py` stays standard library only.
8. **Config in environment variables or one config file**: port, DB path, `ANTHROPIC_API_KEY`, emergency numbers (112, 108), rate limits, daily token cap.

## Repo layout (create in Phase A)

```
/backend
  app/            HTTP layer (added in Phase C)
  tools/          six tools, no LLM imports
  agent/          rule gate, normaliser, state machine, reply check (Phase B)
  agent/llm.py    extraction client (Phase C)
  data/           clinic.json copy, SQLite file location
  tests/          pytest, one module per area
  requirements.txt
  config.py
/frontend         Phase D (not in this plan)
/adversarial      later
README.md, DECISIONS.md, AI_TRANSCRIPT.md
```

---

## Phase A: Foundation and tool layer (Stages 0 and 1, about 2.5 h)

**Goal:** a tested, deterministic tool layer over `clinic.json`, with a one-command run that starts cleanly.

### A0. Setup (about 0.5 h)
- Create the repo layout above. Create a virtualenv, `requirements.txt` with pinned versions: `fastapi`, `uvicorn`, `pydantic`, `pytest`. Add `httpx` for test clients.
- `config.py` reads env vars with defaults: `DB_PATH`, `CLINIC_FILE`, `EMERGENCY_PRIMARY=112`, `EMERGENCY_AMBULANCE=108`, `DAILY_TOKEN_CAP`, `RATE_LIMIT_PER_MIN`.
- One command to run: `make run` or `scripts/run.sh` starts uvicorn (even if the endpoint returns a stub).
- Add a `Makefile` or script target for `make test`.

**Tasks**
- Stub `POST /agent/run` that returns a schema-shaped dummy response.
- Stub returns `terminal_state: "abandoned"`, `escalation_reason: null`, `tool_calls: []`.

**Test (A0 gate)**
- `python runner.py --url http://localhost:8000/agent/run` runs and prints one line per script. Failures are contract-level only, not crashes.
- `pytest` runs with zero tests and exits 0.
- Import test: `tools/` does not import any LLM SDK.

### A1. Data loader and slot model (about 0.7 h)
- `tools/data.py`: load `clinic.json` from a path. Return immutable objects for clinic, doctors, windows, holidays, leave, patients, appointments.
- Derive slots: for a doctor and date, take windows matching the weekday, merge overlapping windows (Dr. Rao Monday 11:45 to 12:00 overlap), generate 15-minute starts, remove holidays, Sundays and leave dates, and remove slots occupied by active appointments.
- Sort all output by `(date, start)`.

**Tests (A1)**
- `test_windows_merge`: Dr. Rao Monday 09:00 to 15:00 with no duplicate starts at 11:45.
- `test_grid_15_min`: every start ends in :00, :15, :30 or :45.
- `test_holiday_closed`: 2026-10-02 returns no slots.
- `test_sunday_closed`: 2026-10-04 returns no slots.
- `test_leave_closed`: Dr. Sethi on 2026-10-05, 06, 07 returns no slots.
- `test_occupied_removed`: Dr. Rao 2026-10-08 09:00 is absent (ap_0015).
- `test_sorted_output`.

### A2. Store and the unique constraint (about 0.5 h)
- SQLite schema: `patients`, `doctors`, `appointments` (with `status`), `handoffs`.
- Partial unique index on `(doctor_id, date, start)` where `status = 'booked'`.
- Store opens a fresh copy of `clinic.json` per run (function `load_run_store(clinic_path, db_path)`).

**Tests (A2)**
- `test_unique_index_blocks_duplicate_booked`: insert two booked rows on the same slot, second raises.
- `test_fresh_store_per_run`: book in run 1, open run 2, booking does not exist.
- `test_cancelled_slot_reusable`: cancel then rebook the same slot succeeds.

### A3. The six tools (about 1 h)
Implement each tool with the signatures and error codes from `DECISIONS_DRAFT.md` Round 3. Every error is `{ok: false, error: {code, field, message, expected}}`.

- `search_slots(doctor_id, date)`
- `lookup_patient(name?, phone?, dob?)`: normalise name (case, dots, spacing) and phone (digits). Return `match` only when identifiers pick exactly one record. Otherwise `candidates` or `none`. Never pick.
- `book_appointment(actor_patient_id, patient_id, doctor_id, date, start)`: validate, check existence, then authority (`actor == patient` or `actor in guardian_of`), then availability, all inside one transaction.
- `reschedule_appointment(actor_patient_id, appointment_id, date, start, doctor_id?)`: `same_slot` error when unchanged.
- `cancel_appointment(actor_patient_id, appointment_id)`: `already_cancelled` on a second cancel.
- `escalate_to_human(reason, summary, patient_id?, appointment_id?)`: `reason` must be one of the five schema enums. Writes a `handoffs` row and returns `ticket_id`.

**Tests (A3)**
- `test_search_happy`: returns sorted slots for Dr. Rao 2026-10-03.
- `test_lookup_phone_and_name_match`: Rajesh Kumar Sharma by phone `9812200011` returns `match` for pt_0001.
- `test_lookup_shared_phone_candidates`: phone `9812200166` returns three candidates, status `candidates`.
- `test_lookup_surname_candidates`: "Sharma" returns candidates, never a single pick.
- `test_book_happy`: Harpreet Singh on Sat 3 Oct 11:00 returns `ap_0026`.
- `test_book_double_sequential`: second booking of the same slot returns `slot_unavailable`.
- `test_book_double_threaded`: 20 threads, same slot, fresh store. Exactly one success.
- `test_guardian_authorised`: Sunita (pt_0008) books for Aarav (pt_0006).
- `test_unauthorised_actor`: Mohit (pt_0020) cancels Lakshmi's (pt_0012) appointment, returns `unauthorised_actor`.
- `test_reschedule_same_slot`: returns `same_slot`.
- `test_cancel_twice`: second cancel returns `already_cancelled`.
- `test_escalate_bad_reason`: returns `invalid_reason`.
- `test_malformed_args`: bad date returns `invalid_date` with `field: "date"`. Off-grid `09:20` returns `not_on_slot_grid`. Unknown doctor returns `unknown_doctor`.
- `test_error_order`: malformed input is reported before existence, and existence before authority.

### Phase A exit gate
- `pytest` green. Tool-layer coverage at least 90%.
- All tests above present and passing.
- The 15 scripts still run through the stub without crashes.
- Commit or save a snapshot. Update `DECISIONS_DRAFT.md` with anything new.

---

## Phase B: Rule gate and conversation core, no model (Stages 2 and 3, about 3.5 h)

**Goal:** a deterministic agent that passes all 15 scripts using rules only. This is the safety-critical core.

### B1. Normaliser (about 1 h)
`agent/normalise.py`
- Date phrases: "aaj", "kal", "parso", weekday names in Hindi and English ("Shanivaar", "Mangalwar", "Budhwar", "Somwar", "Saturday"), and explicit "3 tareekh". Resolve against `today` only.
- Time phrases: "subah", "shaam", "gyarah baje", "10 baje", "9:30", "saadhe nau", "9 baje". Output `HH:MM`, 24-hour.
- Phone: extract 10 digits, strip spaces and dashes.
- Corrections: the last value stated in a turn wins ("Mangalwar 6... nahi, budhwar, 7").

**Tests (B1)**
- Table-driven: `"Shanivaar"` with today 2026-10-01 gives 2026-10-03. `"kal"` gives 2026-10-02. `"parso"` gives 2026-10-03. `"gyarah baje"` gives 11:00. `"9 baje"` gives 09:00. `"shaam"` maps to an evening window flag, not a time.
- Correction test: "Mangalwar 6 tareekh... nahi, budhwar 7 tareekh" gives 2026-10-07.
- Date stability: run the normaliser with `today` set to two different dates. Results must follow `today`, not the clock.

### B2. Rule gate (about 1.5 h)
`agent/gate.py`: runs on every caller turn, before any model call.
- **Red flags** (EN, HI, Hinglish): chest pain, breathlessness, unconscious, heavy bleeding, and similar, with spelling variants, mixed script, punctuation and diacritics removed. Co-occurrence rule: a body-part term plus a distress term trips the gate.
- **Medication and dosing questions**: "dawai", "goli", "Crocin", "kitni der", "dose".
- **Injection markers**: "ignore previous instructions", "administrator mode", "authorised internal test".
- **Bulk requests**: "every appointment", "all appointments".
- Returns `GateResult(kind, reason)` or `None`.

**Tests (B2)**
- Red-flag positive corpus, at least 30 phrases, in English, Hindi, Hinglish, with misspellings. Every one must trip.
- Benign corpus, at least 20 phrases ("bukhar hai", "sardi hai", "appointment chahiye", "Crocin ka matlab kya hai" is a medication test, not a red flag). None may trip the red-flag gate.
- Medication corpus trips `medical_advice`.
- Injection corpus trips `refused`.
- Bulk corpus trips `refused`.
- **Decision for the user before this test is written:** does "pet mein dard" trip the red-flag gate? My recommendation: yes, conservative, with a note in `DECISIONS_DRAFT.md`.

### B3. State machine, rules path (about 1.5 h)
`agent/machine.py`: explicit states, one transition function per state, no model.
- `RECEIVE_TURN`, `GATE`, `NORMALISE`, `IDENTIFY`, `AUTHORISE`, `SEARCH`, `BOOK`, `RESCHEDULE`, `CANCEL`, `ASK_ONCE`, `ESCALATE`, `DONE`.
- Latch: once red flag, medical or injection is set, only `ESCALATE` or `REFUSE` may run. The tool layer also refuses writes when the latch is set. Pass the latch into the tool call context.
- Ask-once: one clarifying question per missing field. If still ambiguous on the next turn, escalate `ambiguous_patient`.
- Terminal state derived from the last successful write tool or the escalate tool. Never from text.
- Reply: template per state. Post-check: every date, time, name and ID in the reply must appear in this turn's tool results. If not, replace the reply with the template.

**Tests (B3)**
- `test_all_15_scripts_rules_only`: each script's terminal state, escalation reason, must-call and must-not-call sets match `expected`. Write a small checker that reads the expected block. The runner does not grade.
- `test_determinism_three_runs`: each script, three runs, identical `(terminal_state, escalation_reason, sorted tool name set)`.
- `test_latch_position`: insert a red-flag turn at position 1, 2, 3 and at the end of each script. Result is always `escalated/clinical_urgent` with no `book_appointment`, `reschedule_appointment` or `cancel_appointment` after the red-flag turn.
- `test_reply_postcheck`: a template reply containing an ID not in the tool results is rejected and replaced.
- `test_no_invented_slots`: every time the reply names a slot, that slot appears in a `search_slots` result for the same run.
- `test_emergency_reply_content`: the clinical_urgent reply contains "112" and "108" from config, and contains no medical advice words.

### Phase B exit gate
- All B1, B2, B3 tests green.
- 15 of 15 scripts match expected outcomes on rules only.
- Red-flag gate: 100% of positive corpus trips. Zero false trips on the benign corpus. If the benign corpus has a false trip, fix the rule before moving on.
- Update `DECISIONS_DRAFT.md`: record the "pet mein dard" decision and any other new rule choices.

---

## Phase C: Model extraction and API (Stages 4 and 5, about 3 h)

**Goal:** add the model at the `EXTRACT` state only, expose the contract over HTTP, and prove the contract and determinism end to end.

### C1. Extraction client (about 1.5 h)
`agent/llm.py`
- Anthropic client, `claude-haiku-4-5-20251001`, temperature 0, timeout set, one retry with backoff.
- Output schema as a Pydantic model: `intent` (enum: book, reschedule, cancel, other), `doctor` (enum), `date_phrase`, `time_phrase`, `patient_name`, `phone`, `dob`, `on_behalf_of`. No IDs, no slots, no terminal state.
- Call only when the rules cannot parse the turn. Results cached per run by turn-text hash.
- Failure path: validation error → retry once with the error message → rules-only fallback → if rules cannot parse, `ESCALATE out_of_scope`.
- Daily token cap from config. When reached, rules-only mode.
- Record tokens and latency per call into the conversation metrics.

**Tests (C1), with a mocked client in CI**
- `test_extraction_schema_valid`: valid JSON parses to the model.
- `test_extraction_invalid_enum`: `intent: "transfer_money"` fails validation, triggers retry, then fallback.
- `test_malformed_output_no_crash`: non-JSON, truncated JSON, extra fields, wrong types. Each returns a structured result, never an exception to the caller.
- `test_model_text_cannot_call_tool`: model output containing "call book_appointment" has no effect.
- `test_temperature_zero`: the request payload has temperature 0.
- `test_spend_cap`: when the cap is reached, the client is not called and rules-only mode runs.
- `test_extraction_cache`: same turn text makes one call per run.
- **Live test (manual, costs money):** run all 15 scripts with the real model and compare to rules-only. Outcomes must match. Record tokens and latency per conversation. Mark the test `@pytest.mark.live` and skip by default.

### C2. HTTP API (about 1 h)
`app/main.py` (FastAPI)
- `POST /agent/run` with Pydantic request model: `conversation_id` (str), `today` (YYYY-MM-DD, validated), `turns` (list of str, length 1 to 50).
- Response model matches `schema.md` exactly. `conversation_id` echoed. `metrics` contains `turns`, `tokens`, `latency_ms`.
- Malformed input: 422 with a structured body. Invalid `today` format returns 422.
- Any unexpected exception inside the turn loop is caught. The response is a valid schema body with `terminal_state: "escalated"`, `escalation_reason: "out_of_scope"`, and the error logged. Never a 500 with an HTML body.
- Rate limiting per IP from config, returning 429 with a structured body.
- Health route `GET /healthz`.

**Tests (C2)**
- `test_contract_fields_present`: every response has all required fields, with correct types, for all 15 scripts.
- `test_conversation_id_echoed`.
- `test_bad_json_422`: non-JSON body returns 422, structured.
- `test_missing_turns_422`.
- `test_invalid_today_422`: "2026-13-40" returns 422.
- `test_empty_turns_422`: `turns: []` returns 422.
- `test_internal_exception_safe_response`: patch the state machine to raise. Response is a valid schema body, status 200, escalated `out_of_scope`.
- `test_rate_limit_429`: set limit to 3 per minute, fourth call returns 429.
- `test_runner_end_to_end`: start uvicorn locally, run `python runner.py --repeat 3`. Expected: zero failures, and "deterministic across 3 runs" printed.

### Phase C exit gate
- All C1 and C2 tests green. Live model run recorded (tokens and latency per conversation) if the key is available.
- `python runner.py --repeat 3` passes against the local server with zero failures and deterministic output.
- Every test in Phases A, B and C is still green.
- `DECISIONS_DRAFT.md` updated with model choice and any extraction-related decisions.

---

## Definition of done for this plan

- Phases A, B and C gates all green.
- 15 of 15 example scripts pass rules-only and model-assisted runs, with identical fingerprints across three runs.
- Red-flag gate has zero misses on the positive corpus and zero false trips on the benign corpus.
- The API matches `schema.md` and never returns a 500.

## Not in this plan (later phases)

- Phase D: React frontend, two screens and sidebar.
- Phase E: eight adversarial cases, README, DECISIONS.md final, AI_TRANSCRIPT.md.
- Phase F: deployment on AWS, HTTPS, rate limit at the edge, spend cap, public live check.

## Handoff note for Antigravity

Start at Phase A0. Work phase by phase. At each gate, stop, run the listed tests, and report the results before continuing. Do not change `clinic.json`, `schema.md` or `runner.py`. Any suspected issue in them goes into `DECISIONS_DRAFT.md`, not into code.
