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
- Accounts (api/accounts.py): each brand <- distributor pair is a folder data/accounts/<id>/ (account.yaml, checked
  against AccountConfig in contracts.py, plus its deals/, emails/, notices/, charges/<month>.csv and data rows; history,
  deliveries, pricing and ops terms load through api/account_rows.py). Peak Bar (peak-bar) is the default everywhere.
  A run belongs to one account: its files, people, distributor, invoice and dispute numbers (dispute_start, +10 per
  later month). Prompts are templated with {brand}, {brand_kind} and {distributor} (api/agents/prompts.py render());
  test_prompts.py proves Peak Bar's render byte for byte as recorded. GET /accounts, GET /accounts/{id}/overview
  (api/overview.py), POST /runs {kind, account}, GET /runs/latest?account=, POST /payments/{account}, GET
  /summary?account=.
- The product always runs live. DEMO_MODE is test infrastructure: the tests replay the recordings in data/fixtures/.
  `make record` runs Peak Bar's whole demo live (March, Dana's answer, April) and saves every AI answer there.
  `python -m api.agents.reader <doc ids>` reads documents.
- POST /runs starts a live pipeline run (api/pipeline.py); `{"fixture": true}` replays the recorded fake run instead.
- QuickBooks (api/integrations/qbo.py): with the QBO_* keys set it writes to the sandbox; without them, or in
  DEMO_MODE, a stand-in answers with "sim-" ids and every ledger post says it's simulated and why. POST /demo/reset
  (`make reset`) deletes the payments and credit memos it wrote and clears its invoice note first. Each write is its
  own ledger post (memo LP-{approval}, note LP-{approval}-note); if one fails, Sam approving again (in the app, or YES
  by text) retries what didn't post with the same request ids, and a 401 fetches a new access token once. Texts
  (api/integrations/sms.py) go out only with the Twilio keys and outside DEMO_MODE; otherwise they wait in GET
  /inbox. Inbound texts: POST /webhooks/twilio/sms (signature checked when TWILIO_AUTH_TOKEN is set).
- A new run of the same payment replaces older ones: their open questions close (Question.closed_at) and an answer
  to a closed one gets 409. Each run numbers its own disputes (March D-0417, April D-0427).
- Every document is read twice (api/agents/readers.py): Reader A is Claude, Reader B is Gemini when GEMINI_API_KEY is
  set and a second Claude prompt until then (the log says which). Re-record Reader B with Gemini once the key works.
- Nessie (api/integrations/nessie.py): with NESSIE_API_KEY and NESSIE_ACCOUNT_ID the app polls the account every 5 s
  and a new deposit whose description names an account (its nessie_description) starts that account's run; POST
  /payments/{account} is the "Northmart pays" button (posts the account's deposit, or starts the run directly without
  keys; /payments/northmart is Peak Bar's); GET /runs/latest?account= finds the run.
- Deployed site (docs/deploy.md): the VM is the single live instance (DEMO_MODE=false). POST /demo/reset needs
  `Authorization: Bearer $CLAWBACK_ADMIN_TOKEN` when that's set; QBO_TOKEN_FILE keeps the rotated QuickBooks refresh
  token in the mounted state/ folder; GET /eval/latest falls back to eval/published/ (`make publish-score`).
- Moss (api/integrations/moss.py, F16): with MOSS_PROJECT_ID and MOSS_PROJECT_KEY (or MOSS_API_KEY) each saved rule is
  indexed by its clause (index model moss-mediumlm),
  and a discretion clause is searched against them; a match at or above `rule_match_similarity` (config/policy.yaml)
  with the same clause type and counterparty applies the rule, otherwise the exact match on type + counterparty does.
  `python -m api.integrations.moss` indexes Rule #1 and prints the similarity of a reworded clause (the Devpost proof).
- Roles and limits (api/auth.py): with OWNER_TOKEN / CONTROLLER_TOKEN set, the in-app owner answer and controller
  approval need that role's X-Clawback-Role-Token; with CLAWBACK_ADMIN_TOKEN set, live runs and other AI requests are
  limited per visitor (the admin token skips it). Texts are checked by phone number and Twilio's signature instead.
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
  Saved rules (with their account) and the audit chain are kept there too (api/db/state.py, migration 004): startup
  restores them, so Rule #1 and /audit/verify survive a restart; POST /demo/reset clears them.
- Value, lookback, packet, owner text: api/engine/value.py puts a run's meters beside its trace (AI calls, cost) and
  charges x policy.yaml `manual_minutes_per_charge` (null: no comparison); the totals events from the end of the gate's
  first pass carry it as `value`, and so does the overview's `current`. api/engine/lookback.py runs every past deduction
  in the six-month window through compute_allowed with terms built in code from history/promo-plan.csv (PA) or the ops
  files (SH/PR/SP); DF and other codes are not_checked. api/lookback.py reads the files (GET /accounts/{id}/lookback,
  the overview's wrongly_taken_6m / lost_past_window / claimable_now); the dispute window is the account's
  `dispute_window_days` ops term (quote checked) else `default_dispute_days`, counted from the payment date, which also
  sets each dispute line's file_by / days_left. GET /portal/disputes/{id}/packet.pdf prints a dispute (api/packet.py,
  fpdf2). Once the gate has decided, the owner gets one summary text (sms.py; its copy is GET /inbox `messages`); it is
  plain code, so the recorded AI requests don't change. The negotiator leaves file_by / days_left out of its request.
- Stub routes serve the fixture run in api/stubs/fixtures.py. After changing it, run `python -m api.stubs.fixtures`
  to rewrite web/fixtures/*.json (a test fails if they're stale).
