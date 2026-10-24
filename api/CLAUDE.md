# api/ (owner: Devank; only Devank edits engine/, agents/, contracts.py)

FastAPI + Pydantic + psycopg 3 (no ORM) on Postgres (Tiger Data). See docs/design.md sections: Agents; Rules engine,
decision gate and approvals; Data model; API, live updates and integrations.

## Build order
1. contracts.py: Pydantic models for Term, Charge, Finding, Decision, Rule, Question, Approval, Dispute,
   PortalMessage, LedgerPost, Event. Stub routes return fixtures. Write web/fixtures/run-events.json (a full
   fake demo run with the exact scenario numbers).
2. agents/reader.py (Claude + Gemini) + quote check → engine/allowed.py + tests → agents/investigator.py →
   engine/gate.py → runs + SSE → questions/rules → agents/negotiator.py → QuickBooks writes + approvals →
   agents/coach.py.

## Hard rules
- Money math only in engine/, with pytest tests reproducing every number in data/CLAUDE.md
  (C1 to C6, April A1/A2, the $540 concession after amendment-1).
- Agents return strict JSON; code checks after every agent (quote found word for word, numbers equal engine
  numbers, evidence IDs exist). Failures route to Ask.
- Only approved senders or documents signed by both parties change a deal (config/policy.yaml).
- No agent posts to QuickBooks. Credit memos over $1,000 need the controller.
- Every outside call: timeout 30 s, one retry, DEMO_MODE fixture fallback. Every action written to audit_log.

## Run it
- `python3.11 -m venv .venv && .venv/bin/pip install -r api/requirements.txt -r requirements-dev.txt`,
  then `source .venv/bin/activate`.
- `make api` serves the stub API on :8000; `make test` runs every test in api/.
- `make record` runs the whole demo live (March, Dana's answer, April) and saves every AI answer to data/fixtures/;
  `make demo` / DEMO_MODE=true replays them with no network. `python -m api.agents.reader <doc ids>` reads documents.
- POST /runs starts a live pipeline run (api/pipeline.py); `{"fixture": true}` replays the recorded fake run instead.
- QuickBooks (api/integrations/qbo.py): with the QBO_* keys set it writes to the sandbox; without them, or in
  DEMO_MODE, a stand-in answers with "sim-" ids and every ledger post says it's simulated and why. POST /demo/reset
  (`make reset`) deletes the payments and credit memos it wrote and clears its invoice note first. Texts
  (api/integrations/sms.py) go out only with the Twilio keys and outside DEMO_MODE; otherwise they wait in GET
  /inbox. Inbound texts: POST /webhooks/twilio/sms (signature checked when TWILIO_AUTH_TOKEN is set).
- A new run of the same payment replaces older ones: their open questions close (Question.closed_at) and an answer
  to a closed one gets 409. Each run numbers its own disputes (March D-0417, April D-0427).
- Every document is read twice (api/agents/readers.py): Reader A is Claude, Reader B is Gemini when GEMINI_API_KEY is
  set and a second Claude prompt until then (the log says which). Re-record Reader B with Gemini once the key works.
- Nessie (api/integrations/nessie.py): with NESSIE_API_KEY and NESSIE_ACCOUNT_ID the app polls the account every 5 s
  and a new Northmart deposit starts the March run; POST /payments/northmart is the "Northmart pays" button (posts the
  deposit, or starts the run directly without keys or in DEMO_MODE); GET /runs/latest finds the run.
- Tests never call live services: api/conftest.py blanks every live key for the session and blocks real Claude clients.
- POST /coach redlines summer-draft from the newest finished March run (api/agents/coach.py); POST /scenario runs a
  pasted clause and charge (api/scenario.py); GET /scenario/examples has three recorded cases.
- `make seed` (api/db/seed.py) applies every file in api/db/migrations/ and upserts data/ through api/rows.py and
  api/documents.py; a second run changes nothing. On TimescaleDB, store_sales is a hypertable and promo_units_weekly
  its continuous aggregate; plain Postgres gets a warning and plain tables. QuickBooks is seeded too when the QBO_*
  keys are set. DB tests: TEST_DATABASE_URL=<throwaway db> pytest.
- With DATABASE_URL set (and not DEMO_MODE) the app runs on Postgres: api/rows.py reads charges, sales, prior payments
  and the promo plan from it (api/db/reads.py, exactly the files' rows; any database error means the files), every
  event is saved to the events table off the run's thread (api/db/events.py), GET /runs/{id}/events and GET
  /runs/latest replay a run after a restart, and GET /db/cap is the cap query. `make db-check` shows all of it.
- Stub routes serve the fixture run in api/stubs/fixtures.py. After changing it, run `python -m api.stubs.fixtures`
  to rewrite web/fixtures/*.json (a test fails if they're stale).
