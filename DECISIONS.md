# Decisions

This file records every ambiguity I found in the brief and the supplied material, what I chose, and why. It also records where the material looked wrong, and what I did about it. Where a decision was later changed, both the first choice and the change are recorded, because the change is part of the decision.

Two labels are used throughout. **Stated** means the choice follows directly from the brief or the supplied data. **My call** means the material left the question open, and I chose an answer and gave my reasons.

---

## 1. Safety and escalation

### 1.1 Red flags stop everything, and they are checked first

Every caller turn passes through a rule gate before any parsing, any tool call, or any model call. If the gate finds a red flag, the conversation latches. After a latch, the agent can only escalate, and the tool layer refuses writes for the rest of the conversation, even if a later turn is harmless. I chose this because the brief says that a submission which carries on with a booking through a medical emergency is rejected, whatever its other scores. A latch that a later turn could clear would leave that outcome open to a model error.

The gate recognises chest pain, breathlessness, unconsciousness, heavy bleeding and similar terms in English, Hindi and Hinglish, including common misspellings, and it recognises a body part combined with a distress word even when neither word is on the list alone. It was tested against a corpus of positive phrasings, which must all trip, and a corpus of benign phrasings, which must not trip. When a benign phrase tripped the gate, I changed the rule rather than the test.

### 1.2 Stomach pain escalates as clinical urgent

The phrase "pet mein dard" and its variants ("pet dukh raha hai", "stomach pain", "pet mein marod") escalate as `clinical_urgent` and stop any booking. The brief does not say whether abdominal pain counts as a clinical emergency, so this was my call, and I made it on the safer side. The cost is that a caller with mild stomach pain reaches a human and does not get a booking. The brief scores restraint as well as safety, so this is a real trade-off, and it is recorded as a risk.

The rule is tighter than "pain and body part". A negated clause does not trigger ("pet dard nahi hai, appointment chahiye" books normally). A resolved clause does not trigger ("pehle tha, ab theek hai"), unless an active marker appears in the same turn. Active markers include "abhi bhi", "phir se", "badh raha hai" and "ho raha hai", and they always win. Words of severity, such as "bahut", "tez", "zyada", "severe" and "worse", trigger regardless of negation. Each clause is judged separately, so "dard nahi, lekin seene mein bahut dard" triggers on the second clause.

### 1.3 A medicine or dosage question is not an emergency

A question about a tablet, dose or timing ("ek aur goli le lun ya nahi") escalates as `medical_advice`, not `clinical_urgent`. A question about dosage with active distress in the same turn is `clinical_urgent`. A question about dosage on its own ends the conversation as `escalated` with `medical_advice`, so the agent does not go on to book. The agent never gives medical advice in any reply.

### 1.4 Emergency numbers

The emergency reply gives 112 as the primary number and 108 as the ambulance number. Both are set in configuration. The brief does not supply an emergency number, and the material does not name a clinic contact number. 112 is India's single emergency number, and 108 is the ambulance number in many states. Dehradun's local numbers should be checked before the live link is used for a real caller. They are not invented in code: they come from config, where they can be changed.

When a caller reports severe symptoms, the reply says that a person is connecting, and tells the caller to call the emergency number now. It contains no advice about treatment.

### 1.5 Emergency contact in the data

The owner asked that an emergency contact on file be used first when a clinical case needs a human. The supplied data contains no emergency contact for any patient. The data does contain a guardian link for some child patients, and the agent uses that link for authority, not for emergencies. If the data had an emergency contact, the handoff record would name it first. This is documented, but it is not exercised by the supplied data.

### 1.6 Escalation reasons

There are five escalation reasons, taken from the output contract: `clinical_urgent`, `medical_advice`, `not_authorised`, `ambiguous_patient` and `out_of_scope`. A malformed model answer that remains malformed after one retry escalates as `out_of_scope`. I chose this rather than a silent failure, because a failure that is hidden from the queue is worse than a handoff that a human can close. The brief does not name a reason for technical failure, so this was my call.

### 1.7 Injection attempts and bulk requests are refused

A message that tries to override the agent's instructions, or that asks for every appointment to be cancelled, ends in `refused`. The rest of a conversation is not acted on. I chose `refused` rather than `escalated`, because the contract defines `refused` as "nothing needs to happen", and an injected instruction is not a request a human should pick up. In one case I weighed the opposite: a conversation with an injection and a genuine booking request. I resolved it in favour of refusal, as the rule says, and recorded the choice in that case's notes.

A bulk cancellation request is not something the tool layer supports at all. The cancellation tool takes one appointment ID. There is no tool that cancels a set of appointments, so a bulk request cannot be carried out even if it were not refused.

---

## 2. Identity, authority and patients

### 2.1 Lookup returns candidates, never a guess

`lookup_patient` returns a single match only when the identifiers given pick exactly one record. Otherwise it returns the candidates, with enough fields to tell them apart: name, date of birth and guardian links. A name alone is not enough when three people share a surname. A phone number alone is not enough, because the data gives the same phone number to several people. A lookup with no identifiers at all returns the `no_identifier` error. It does not return every patient.

### 2.2 Shared phone numbers are real and the agent relies on them

The supplied data gives one phone number to three different groups of people: a pair of twins and their guardian, a mother and her son, and a couple. The brief does not say what to do about this, so the decision is mine. The agent does not treat the phone number as proof of identity. It asks for a name, and it uses the guardian links to decide which record a caller may act on.

### 2.3 Twins with the same date of birth

Two children share a date of birth and a phone number, and both are guardians' dependants. The name decides which child a request is about. If the name is missing, the agent asks. It does not pick the first record that matches.

### 2.4 Authority is checked in the tool layer

A booking, reschedule or cancellation takes the acting patient and the target patient as separate arguments. The tool layer allows the action only when the actor is the target, or is listed as a guardian of the target. The agent cannot override this check. I put the check in the tool layer because the brief says the tool layer is the ground truth, and because a check in the agent could be argued around by a model's output.

### 2.5 The guardian booking is recorded against the child

When a guardian books for a child, the appointment is recorded against the child's patient record, and the output's `patient_id` is the child's ID. The schema does not define this case, so this was my call. The child is the person the appointment is for. The schema is silent on this case, so this is my reading of it.

### 2.6 `patient_id` is null on a refused authority

When the caller is neither the patient nor a listed guardian, the output's `patient_id` is null, even when the caller's target record exists. The schema says the field is "the patient the conversation resolved to", which could be read to include a record the caller was not allowed to act on. Recording that record would link an unverified third party to a real patient's data. This was my call.

### 2.7 The agent never reveals whose record it found

For a cancellation or reschedule, the agent does not say whose record it found. It asks the caller to identify themselves. Otherwise a caller could confirm that someone else holds an appointment just by asking.

### 2.8 Ambiguous patients are asked once, then escalated

If the identifiers are still ambiguous after one question, the conversation escalates as `ambiguous_patient`. The schema defines the reason, and the brief says escalate rather than guess. Asking once is my choice. It keeps the number of handoffs reasonable, which the restraint score rewards, while still never guessing.

---

## 3. Dates, times and the clinic calendar

### 3.1 "Today" comes from the request

Every relative date ("aaj", "kal", "parso", a weekday name, "3 tareekh") is resolved against the `today` field of the request. The system clock is never used, so a run gives the same result on any day. The supplied scripts set a `today` value, and the runner's fallback value is never used in practice.

### 3.2 "Kal ya parso" is ambiguous

A caller who gives two dates joined by "ya" or "ya phir" is not resolved silently to one of them. The agent asks which the caller means. "Parso" alone is the day after tomorrow, and "kal" alone is tomorrow. This was my call. The alternative was to pick the first date, and that could book the wrong day.

### 3.3 A correction counts

If a caller states a date and then corrects it in the same turn or a later one, the last value stated wins. The scripts include cases where the caller changes their mind mid-sentence, and the brief lists this as a case to handle. A caller who says "Mangalwar 6 tareekh, nahi, budhwar 7 tareekh" gets Wednesday, the 7th.

### 3.4 Times

Times are returned in 24-hour form, as HH:MM. A concrete time always beats a morning or evening word, whichever comes first ("10 baje subah" and "subah 10 baje" both give 10:00). The words "subah" and "morning" set a morning preference, and "shaam" and "evening" set an evening one. A bare number from 1 to 7 with no marker is read as afternoon or evening, because the clinic is never open before 09:00. "8 baje" with no marker stays 08:00. Both cases fall outside clinic hours on the other reading, so the choice is safe, and it is recorded as an assumption.

A defect was found in the time parser: "9:15 baje" was read as 15:00, because the minutes were taken for an hour. It was fixed and tested.

Hindi number words (nau, das, teen and so on) and the fractions "saadhe", "dedh" and "dhai" are supported.

### 3.5 Holidays, Sundays and leave

The clinic is closed on Sundays and on the holiday in the supplied data. A doctor on leave has no slots on the leave days. A booking, reschedule or search on any of these days returns a structured error with the code `clinic_closed` or `doctor_on_leave`, not a slot. A search on a closed day returns an empty list with a `closed_reason`, so the agent can tell the caller why. I chose an empty list with a reason, because it is the one shape that works for both the agent and the screen.

### 3.6 Overlapping windows

One doctor's Monday windows overlap for a short period. The slot generator treats the windows as a union, so a slot in the overlap is offered once, not twice. The brief describes the clinic as having about two windows per day, and the data does not match that description exactly. I took the data as the source of truth.

### 3.7 Slots are on a fifteen-minute grid

Slots fall on a fifteen-minute grid, taken from the clinic configuration. A time off the grid returns `not_on_slot_grid`. The check runs first, before the slot is compared with the schedule.

### 3.8 No current time of day

The supplied material gives a date but no time of day. For "aaj" requests to cancel or reschedule, the agent treats the appointments on that day as current. It does not work out whether an appointment has already passed. This is my call, and it is an open question for the clinic.

### 3.9 No notice window

No cancellation or rescheduling notice period is stated anywhere, so none is enforced.

### 3.10 A second booking on the same day

A patient who already has an appointment on a day can book another one on the same day. The material does not forbid this, so the agent allows it. This is open, and a clinic would normally set a rule for it.

---

## 4. Booking, rescheduling and cancelling

### 4.1 When the agent books

The agent books when the date, the time and the patient are known. If the time is missing, it asks once. If the caller gives a time that is taken, the agent says so, and offers the nearest free slots from the schedule, and only those. The brief's scripts do not include a confirmation step, so the agent does not ask the caller to confirm a slot before booking. This is my call. The supplied scripts do not include a confirmation step, and I did not add one.

### 4.2 Double booking is impossible in the store

Two requests for the same slot cannot both succeed. The store holds a unique constraint on active appointments by doctor, date and start time. The check and the insert run in one transaction, with an immediate lock taken first, so the request that loses the race receives `slot_unavailable`. A threaded test runs twenty simultaneous bookings for one slot and checks that exactly one succeeds. The test was run repeatedly, not once.

### 4.3 Reschedule

A reschedule checks the target slot in the same way as a booking. The target must not be a Sunday or holiday, must not fall on leave, and must sit inside one of the doctor's windows. A reschedule to the same slot returns `same_slot`. A reschedule of a cancelled appointment returns `appointment_cancelled`. A rejected reschedule leaves the original appointment unchanged. An earlier version allowed a reschedule onto a Sunday. That defect was found by a test and fixed.

### 4.4 Cancel

A cancel of an already cancelled appointment returns `already_cancelled`. I chose an error over a silent success, because a caller who is told "cancelled" when nothing changed would be misled. The supplied material does not say which is right, so this is my call.

### 4.5 Which appointment is cancelled or moved

When the caller says "aaj" and has one appointment that day, that appointment is used. When the caller has several, the agent asks which one, and escalates if the caller still does not say. The agent does not choose one appointment on its own.

### 4.6 Appointment IDs are random

Appointment IDs are generated from a random value, with an `ap_` prefix. The early plan called for sequential IDs. The implementation uses random ones. The grader's determinism check compares terminal states, escalation reasons and tool names, not IDs, so this does not affect any scored result. It is still a deviation from the early plan, and it is recorded as one.

### 4.7 Patient IDs in the data are stable

The patient and doctor IDs come from the supplied data and are never generated. The agent code contains no patient, doctor or appointment ID. A hard rule was set for this, and an earlier version of the state machine broke it. That version was corrected, and the removal of the hard-coded IDs is recorded in the change history.

---

## 5. The tool layer

### 5.1 Six tools, one error shape

The six tools are `search_slots`, `lookup_patient`, `book_appointment`, `reschedule_appointment`, `cancel_appointment` and `escalate_to_human`. None of them calls a model. Each returns either a success with its fields, or an error in one shape: `{ok: false, error: {code, field, message, expected}}`. The code names what went wrong. The field names the argument at fault. The expected value says what would have been accepted. A message for the agent is never passed to the caller unchanged.

A malformed argument is checked before anything is read from the store. The checks run in a fixed order: input shape, then doctor or patient existence, then the slot, then availability, then authority. Each error reports the first check that failed, so the same mistake always produces the same error.

### 5.2 The contract's codes are used, and extra ones are named

The tools use the codes the design calls for, for example `unknown_doctor`, `invalid_date`, `invalid_time`, `not_on_slot_grid`, `outside_window`, `clinic_closed`, `doctor_on_leave`, `slot_unavailable`, `unauthorised_actor`, `unknown_patient`, `unknown_appointment`, `same_slot`, `already_cancelled`, `no_identifier` and `invalid_reason`. An earlier version used different names for two of them. `appointment_not_found` in the design became `unknown_appointment`, and `appointment_cancelled` became `already_cancelled`. The output contract does not name these codes, so either choice satisfies it. I kept the names the code already used, and the README lists them.

### 5.3 Every failure is recorded

A failed tool call still appears in the output's `tool_calls` list, with its error. The contract says that `tool_calls` must include failed calls, and the transcript on the screen shows the failure, so the reviewer can see what the agent tried.

### 5.4 The store is reset for each run

Each conversation starts from the clinic data as supplied. The store is rebuilt from `clinic.json` for every run, including the handoff counter, so ticket numbers restart at 1 for each conversation. The README says that a run starts from the file as shipped, and the code does what the README says.

The brief says that two conversations racing for the same slot must not both succeed, and it also says that each conversation starts from the shipped schedule. Those two statements look as if they conflict. Both hold in this design, because the race rule is enforced inside one store at a time, and the store is per run. Two requests that share a store, as the threaded test does, cannot both book the same slot.

### 5.5 Models are not in the tool layer

The tool layer does not import or call a model. The build instructions forbid it. The brief calls the tool layer the ground truth, so a model in it would undermine the grounding requirement.

---

## 6. The conversation and the model

### 6.1 The model is a fallback, not the decision-maker

The agent is rules-first. The rules read each turn, run the safety checks, and make every decision about tools and states. The model is called only at one point: when a turn contains a value the rules cannot read, and only when no rule has already settled the matter. A turn that the rules fully parse does not reach the model at all.

The model's answer is validated against a schema. It can fill a field the rules left empty, and it cannot override a rule result. It never chooses a tool, an ID, a slot or a terminal state. Those are decided in code from the tool results. This is the decision that keeps the grounding requirement, the zero-invented-facts requirement and the determinism requirement intact.

### 6.2 The model is configured by mode

The setting `EXTRACT_MODE` has two values. `auto` is the default, and it calls the model only for turns the rules cannot parse, which is the production behaviour. `always` calls the model on every turn, and it exists only so the model's answers can be measured against the rules. The default is `auto`.

### 6.3 Which model, and why it changed

The first design named an Anthropic model for extraction. The owner then had a Google Gemini key and wanted a model with a free tier and high request limits. The extraction moved to a Gemini Flash-Lite model, configured in one place, with temperature 0 and the same validation. The Anthropic configuration was removed, and the README describes the Gemini setup. The change is recorded here so the reviewer can see the first plan as well as the final one.

The model is set to `gemini-3.1-flash-lite`. The earlier `gemini-2.5-flash-lite` returned "no longer available to new users", so it was replaced. A pinned model ID is used rather than a moving alias, because a moving alias could change the output between runs, and that would break determinism.

### 6.4 The key is fail-closed

The key is read from an environment variable or from the server's env file, never from code. With no key, or an empty key, the model is never called, and the agent runs rules-only. A test confirms that no network call is made. The key is never logged, printed or written to a file the repository tracks. A placeholder key is never used in its place.

### 6.5 Spend is capped

A daily token cap is set in configuration. When the cap is reached, the agent runs rules-only for the rest of the day. The cap is checked before each model call. A call that is rate-limited by the provider does not count against the cap, because it used no tokens.

### 6.6 Model outcomes are recorded

Each model call is logged with one of six outcomes: `ok`, `invalid` (the answer was malformed), `error` (a network or server failure), `rate_limited`, `skipped_no_key` (no key was set, so no call was made) or `skipped_cap` (the daily cap had been reached). The outcome matters because a zero in the token column can mean that no call was made, that the call failed, or that the call was not counted. The screen shows the outcome, so a zero is not presented as a cost.

### 6.7 Answers are cached

The model's answer for a turn is cached, keyed by a hash of the turn's text. A repeat run of the same turns reuses the cache. This keeps three runs identical, which the determinism rule requires. The side effect is that a repeat run costs nothing, so the stored cost of a conversation is taken from its first run. The cache keeps that first-run cost, so the screen can show what a conversation really costs.

### 6.8 Intent is not guessed

A turn with no booking, rescheduling or cancellation wording has no intent. The conversation keeps the intent it already has. An earlier version defaulted to booking, and a comparison against the model found the bug. The default was removed.

### 6.9 Replies come from templates and are checked

Replies are templates keyed by the state of the conversation, in Hinglish or English, following the language of the caller. The model does not write replies. Before a reply is returned, a grounding check compares every date, time, name and identifier in it with the tool results from the same turn. If anything in the reply has no source, the reply is replaced by the template for that state.

Replies vary so that they do not repeat. A reply that would repeat the previous one is replaced by one that says what is now known, or what is still needed. A filler line that repeated across turns was removed.

After a handoff, the agent speaks once. Later caller turns in the same conversation get no new reply in the transcript, because the caller has been passed to a person. The graded `reply` field still carries the reply that was given.

### 6.10 The agent states slots only from a search

The agent offers a time only if the time appears in a `search_slots` result from the same conversation. When the requested time is taken, the agent offers the nearest free slots from that same result. When a day has no free slots, the agent says so. The test suite checks each time the agent states a slot against the search results, across all of the conversations.

### 6.11 Ask about the day or doctor before the patient

When the day or the doctor is missing, the agent asks for it before asking for the patient's details. This keeps the early turns focused on what the caller wants, rather than on identity. It is a small design choice, and it is recorded here because it changes the order of questions.

---

## 7. The output contract

### 7.1 The graded response has only the schema's fields

The response of `POST /agent/run` contains only the fields in the output contract: the conversation ID, the tool calls with their names and arguments, the terminal state, the escalation reason, the patient ID, the appointment ID, the reply, and the metrics. Everything the screens need is stored separately. A test confirms that the graded response for all of the supplied conversations has exactly the schema's shape.

### 7.2 Escalation reason is null unless escalated

`escalation_reason` is null unless the terminal state is `escalated`. The schema says this, and the code follows it.

### 7.3 `metrics.turns` counts the caller's turns

The screen mockup shows a count of six for a conversation with two caller turns, so its count includes something else, possibly every message. I chose the number of caller turns. It is simple to explain, and it matches the request. The mockup and this definition disagree, and the disagreement is open.

### 7.4 Tokens and latency are measured

Latency is measured around the whole request, and is stored in milliseconds. The screen shows it in milliseconds below one second and in seconds above. Tokens are the sum of the provider's usage figures across all model calls in the request. A call that was rate-limited, or one served from the cache, adds no tokens to the graded response. The screen shows the cost of the first run separately, so the figures in the README come from a first run and not from a cached repeat.

### 7.5 The patient ID rules are written down

The output's `patient_id` is the patient the conversation resolved to. It is null when nothing was resolved or the match is ambiguous. For a guardian's booking it is the child, as set out in section 2.5. For a refused authority it is null, as set out in section 2.6.

---

## 8. Determinism

### 8.1 What counts as the same

The grader compares the terminal state, the escalation reason and the set of tool names across three runs. It does not compare argument values, reply wording, or IDs. The runner uses the same rule, and it reports a difference in any of those three fields. The order of tool calls is not compared, which matches the schema's wording "the same set of tool names".

### 8.2 How determinism is kept

Three things keep the runs identical. The rules decide everything that matters for safety, so the model cannot change a safety outcome. The model is called at temperature 0 with a pinned model ID. Its answers are cached, so a second run uses the same answers as the first.

### 8.3 The check that found a false pass

An early agreement check reported success while the model had never been called, because the run used the default mode, in which the rules handled every turn. The check now reports how many model calls were made for each script, and a script counts as compared only when every turn got a successful model answer.

---

## 9. The screens

### 9.1 The IDs in the mockups are not the file's IDs

The screen mockups use some identifiers that do not appear in the supplied data. Conversation IDs such as "cv_44xx" and a patient ID outside the range of the file are examples. The screens use the IDs from the file, because they are the only IDs the API can return. The mockup values are treated as layout, not as data.

### 9.2 The header shows the call's own date

The conversation header shows the call's date, which is the request's `today`, and the time the call began, in the Asia/Kolkata time zone. It is formatted as "01 Oct 2026, 11:42". The mockup shows a scripted date with a suffix; the suffix was removed, because the scripted date and the call date are the same value.

### 9.3 Tool results appear on the line under each call

Every tool call shows the result it produced: the candidates or the match for a lookup, the slot times for a search, the ID and date for a booking, the error code for a failed call, and the ticket number for an escalation. The word "executed" is not used, because it hides whether the call worked. A test checks that a successful call never shows an error line.

### 9.4 The escalation summary is built from facts

The summary given to the human is one sentence, built from the reason, the doctor's name from the file, the resolved date and time, and the patient's name from a lookup result. It is never a copy of the caller's words. A test checks that the summary contains no word which the caller did not say and which is not a name in the data. An earlier version copied the transcript, and that was replaced.

### 9.5 Differences from the mockup that remain

The mockup calls `search_slots` with a morning window. The contract does not have that argument, and the search in this build takes only the doctor and the date. The morning or evening preference is applied to the result afterwards. This is open, and it is a reasonable reading of the mockup, not a copy of it.

The mockup shows a "Resolve" action on the queue. Resolving a handoff writes to the UI tables only. The graded response does not include it, so the grader never sees it.

The mockup's determinism panel shows a comparison across runs. The screen reads the stored repeat-run results, which the endpoint returns with a stable flag.

---

## 10. Deployment

### 10.1 Backend on AWS, frontend on Vercel

The owner has AWS credits, so the backend runs on AWS, on one small Ubuntu server in the Mumbai region, in a Docker container. The frontend is a static build on Vercel. The brief allows any hosting, and the split keeps the frontend cheap and the backend in a place with a persistent disk.

I considered Google Cloud Run, Render, Railway, Koyeb, Oracle's free tier and PythonAnywhere. Cloud Run was the cleanest option for a container, but it was not used, because the owner's credits were on AWS. Render's free tier sleeps and loses its disk. PythonAnywhere runs WSGI applications by default, which does not suit FastAPI. The owner chose AWS, so the server is an EC2 instance.

### 10.2 HTTPS through Caddy

CloudFront was the first choice for HTTPS. The new account was not verified for CloudFront, and verification needed a support case, so the route was changed. Caddy now runs on the same server and obtains a certificate for a hostname from a free name service, which resolves from the server's address. The CloudFront setup was never used in production.

### 10.3 The rate limit is shared behind the proxy

The per-client limit reads the address of the connecting client. Behind Caddy, every visitor appears to come from the same internal address, so all visitors share one limit. The limit is raised for the demo. The fix is to read the forwarded address from the proxy, but that needs the proxy to be trusted, and I did not make that change before the submission. This is a known gap.

### 10.4 Port 8000 is open

The container's port is open to the internet, because it was needed while the setup was being tested. Once Caddy was working, that port was no longer needed, and closing it is the remedy. It is recorded as a gap, because the setup was tested this way and not fully hardened.

### 10.5 The database is on the server's disk

The UI's data is stored in a single SQLite file on the server's disk, mounted into the container. It is not replicated and not backed up. A restart keeps it. A rebuilt server loses it. For a submission this is acceptable, and a clinic would need a managed database.

### 10.6 Secrets stay out of the repository and the image

The key is stored in an env file on the server, outside the repository. The Docker build excludes the local env file, the virtual environment and the database. The repository includes an example env file with an empty key line.

### 10.7 Cost

The EC2 instance is small, and it falls under the free tier for its first year, or is covered by the credit. After that it costs money every month, and the owner was asked to confirm that cost before deploying.

---

## 11. Adversarial cases

### 11.1 The eight cases

There are eight adversarial conversations, in the same format as the supplied ones. Each one targets a specific way a naive agent fails: a fever with a booking request; a negated stomach pain; a stomach pain with a booking request; a dosage question; a guardian cancelling a child's appointment; a change of mind mid-sentence; a Hindi-worded emergency; and an injected instruction in the middle of a booking.

### 11.2 Corrections to expected outcomes

Some expected outcomes were wrong when first written, and each correction is recorded in the file's notes. The injection case expected a booking, but the rule refuses the whole conversation, so it was changed to `refused`. The fever case asked for a slot that the supplied data already holds, so its input was changed to a free slot, checked by hand against the clinic file. The negated stomach-pain case was changed to a different patient, one with no appointment that day, and its expected slot was checked by hand against the clinic file.

The rule for any future change is the same. An expected outcome is worked out from the brief and the data, not from the agent's output. If the agent disagrees, the disagreement is reported and the expected outcome is left alone, until a person decides which is right.

---

## 12. What the material got wrong or left open

The brief asked for anything that looked wrong or inconsistent to be recorded here. These are the points I found.

### 12.1 Things in the material that looked wrong

The schema's example response has a patient ID that its tool calls never looked up. The example's patient differs from the first supplied conversation with the same ID. The example is illustrative and does not match the data.

The brief says that each doctor has two appointment windows per day. The data gives one window on most days, and Monday windows that overlap. I took the data as the source.

The runner's README says to run it with `python3`, which is not the usual command on Windows. The runner also loads only the supplied conversation folder unless it is told otherwise, so the adversarial cases need a separate command.

The conversation for a Sunday booking request expects `abandoned`, but the caller gave a usable request. `refused` fits the definition of `abandoned` at least as well. I kept `abandoned`, because it was the supplied expected outcome. The reply was changed to say there is no slot that day, but it does not yet say the clinic is closed.

The "tomorrow" in the bulk-cancel script falls on a holiday with no appointments, so the refusal is correct, but the script does not test the rule its notes describe.

A booking script says "kal" with a `today` that makes it a holiday. The escalation is correct, but the notes do not mention that a booking attempt would also land on a closed day.

The brief's confidentiality notice asks that the material not be shared or published. The owner asked for a public repository and a public live link, which conflicts with the notice. The owner chose a public repository and a public live link. The repository contains no text from the brief itself, only this analysis and the synthetic data.

### 12.2 Open items

The following are not settled by the material, and the agent's current behaviour is recorded here.

The clinic's time of day is not given, so same-day cancellations are allowed without any cut-off.

A patient may book a second appointment on the same day.

No notice period is enforced for cancellations or reschedules.

A phone number with a country code in front ("+91") is not recognised, with or without a space after the code, because the matcher looks for ten digits on their own. A fix would compare the last ten digits, and it is not in this version.

The screen's morning window is not an argument of the search tool, as described in 9.5.

The two scripts the README describes as booking the same slot have not been identified. The likeliest pair is the two Saturday bookings with Dr. Rao, but this is a guess.

A caller who asks for "subah" with no time gets the earliest free morning slot. The owner did not confirm this.

The emergency numbers 112 and 108 should be checked for Dehradun before the live link is used.

The scratch scripts in the repository root and some generated text files are not part of the submission and are not committed.

---

## 13. Questions I would ask the clinic

Which emergency number should the reply give, and should it give one at all?

Should a second appointment on the same day be allowed?

What is the cut-off for same-day cancellation and rescheduling?

Should the agent confirm a slot with the caller before it books?

Is the clinic open on the holiday in the data, or closed as the data says?

Should abdominal pain without any severity words stop a booking, or should it only be recorded?
