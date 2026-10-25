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
- No agent posts to QuickBooks. Credit memos over $1,000 need the admin's yes (the owner, the one person who decides),
  unless they're within the auto-post limit the admin set.
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
  own ledger post (memo LP-{approval}, note LP-{approval}-note); if one fails, Dana approving again (in the app, or YES
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
- Three sources start runs with no clicks, all through pipeline.start_for_deposit (once per arrival; a second source
  seeing the same payment within 30 minutes, same amount, is matched to the run the first one started), and each
  notes what it saw for GET /connections?account= (api/sources.py, memory only): the bank (Nessie, above);
  QuickBooks (api/integrations/qbo_source.py: with the QBO_* keys, outside DEMO_MODE, QBO_POLL not off, every 15 s a
  payment recorded against an account's invoice starts its run; what's there on the first look and Clawback's own $0
  payments never do; reads never recorded as fixtures; `python -m api.integrations.qbo_source pay <account>
  [--replace]` records the distributor's payment in the sandbox for the demo); and the remittance inbox
  (api/inbound_email.py, POST /webhooks/inbound-email, a Mailgun route; MAILGUN_WEBHOOK_SIGNING_KEY, INBOUND_EMAIL_DOMAIN,
  INBOUND_EMAIL_DIR, INBOUND_EMAIL_FORWARDERS): signed, handled once, routed by address / desk / invoice; a remittance
  from a trusted, SPF-authenticated sender is read and checked like an upload and starts the run on its lines; any
  other email becomes a document of the account (accounts.inbound_root(), Account.inbound) that its next run reads
  after the deal_docs (pipeline.documents_of): an authenticated approved sender's can change the deal, anyone else's is
  a claim.
- Deployed site (docs/deploy.md): the VM is the single live instance (DEMO_MODE=false). POST /demo/reset needs
  `Authorization: Bearer $CLAWBACK_ADMIN_TOKEN` when that's set; QBO_TOKEN_FILE keeps the rotated QuickBooks refresh
  token in the mounted state/ folder; GET /eval/latest falls back to eval/published/ (`make publish-score`).
- Moss (api/integrations/moss.py, F16): with MOSS_PROJECT_ID and MOSS_PROJECT_KEY (or MOSS_API_KEY) each saved rule is
  indexed by its clause (index model moss-mediumlm),
  and a discretion clause is searched against them; a match at or above `rule_match_similarity` (config/policy.yaml)
  with the same clause type and counterparty applies the rule, otherwise the exact match on type + counterparty does.
  `python -m api.integrations.moss` indexes Rule #1 and prints the similarity of a reworded clause (the Devpost proof).
- Sign-in and tenancy (api/users.py, api/tenancy.py, api/routes/auth.py, migration 006): POST /auth/login {email,
  password} sets the clawback_session cookie; GET /auth/me; POST /auth/logout. Users in config/users.yaml (passwords from
  DEMO_USER_PASSWORD / DEMO_USER2_PASSWORD). Every account-data route takes `who: Caller = Depends(current_supplier)`
  and checks ids with tenancy.account_or_404 / can_see_run: another supplier's ids are 404, signed out 401 once any
  password is set; no password anywhere (laptops, tests) stays open. Tokens (OWNER_TOKEN, CLAWBACK_ADMIN_TOKEN) see
  every supplier. api/tests/test_tenancy.py walks every Peak Bar route as Lantern Hill.
- Dispute email (api/dispute_email.py, api/agents/email_writer.py, api/integrations/gmail.py, mailgun.py, routes
  api/routes/dispute_mail.py, migration 007): runs file disputes as ready_to_send; GET /disputes/{id}/email drafts the
  email in the app (Claude, checked by the outbound filter, one retry, then held; the code template when the call
  fails); PUT edits it; POST /disputes/{id}/send is the admin's approval: sent over Gmail SMTP (smtp.gmail.com:465 SSL,
  GMAIL_ADDRESS + GMAIL_APP_PASSWORD) from the supplier's address with the packet PDF, our Message-ID saved and [D-n]
  in the subject; Mailgun when only its keys are set; the in-app outbox with neither or in DEMO_MODE; then filed. The
  Gmail poller (GMAIL_POLL, IMAP, 30 s) matches replies by In-Reply-To / References or [D-n] and runs disputes._post;
  the Negotiator's answer waits as a reply email (POST /disputes/{id}/replies/{email_id}/send); GET /notifications.
  policy.yaml auto_send (default false).
- Google Drive (api/drive.py, routes api/routes/drive.py, migration 008): with GOOGLE_SERVICE_ACCOUNT_JSON and
  DRIVE_ROOT_FOLDER_ID, a poller (30 s, Changes API) versions each file in <Supplier>/<Distributor>/{Contracts,
  Promotions, Remittances, Correspondence, Sales data} by sha256; contracts and notices become account documents under
  DRIVE_DOCS_DIR (Account.drive, read by runs), a signed amendment under an open dispute concedes through
  disputes._new_document, a remittance starts a run; POST /drive/sync; the Drive card in library.connections().
- Question risk (api/engine/question_risk.py, policy.yaml question_risk): each owner question carries risk {level,
  kind, reason} and details [{label, value}], from the engine's numbers and the clause in code (no AI call), set in
  pipeline._question_risk. Northmart's C6 is high / relationship. The fixture run's Q-1 carries the same.
- One admin (api/auth.py): the brand's owner answers every question and approves every credit memo, in the app or by
  text to OWNER_PHONE (there is no controller; account.yaml's brand.controller is still accepted and unused). With
  OWNER_TOKEN set, the in-app answer and approval need it as X-Clawback-Role-Token; POST /questions/{id}/answer takes
  `save_rule` (default true; false settles this charge only and saves nothing), POST /approvals/{id} takes `auto_post`
  (default false; true saves the account's auto-post limit at this memo's amount, kept in auto_post_limits by
  api/db/state.py, migration 005, and later fair-charge memos up to it post without asking, audited as
  auto_post:<name>; policy.yaml `auto_post_limit` is the default, null). With CLAWBACK_ADMIN_TOKEN set, live runs
  and other AI requests are limited per visitor (the admin token skips it). Texts are checked by phone number and
  Twilio's signature instead.
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
- Fee schedules (api/engine/allowed.py "Fee schedules"): a charge whose code the deal names in a fee_schedule term
  (directly or via FeeData.codes) is priced from the other side's backup lines (FeeData.lines, keyed by the charge's
  ref): % with min / max per invoice, PO, incident or month, per unit, per carton, per PO or flat, tiered by days,
  plus any cost passed through at cost. A policy change counts from max(effective date, notice date + notice_period).
  A deal's dispute_window is checked for every charge against FeeData.as_of; past it the gate accepts with a note
  (row 10). An account with data/accounts/<id>/fees/fees.yaml (api/fee_accounts.py: codes, policy changes, as_of,
  older charges, fees/backup.csv, purchases/) runs through the same pipeline with those passed in; its readers also get
  prompts/reader_fees.md (reader.with_fees), so Peak Bar's requests stay byte for byte as recorded. account.yaml
  `contracts:` names real contracts under data/contracts/ that are the account's documents (KeHE's for lantern-hill;
  Walmart's for copperline; Five Below's two versions for fizzwick, each signed by both). A fee_schedule can also say
  which PO type it applies to (applies_to, against purchases' po_type), that it's a remedy for the supplier's own
  failure (requires_fault, against deliveries/appointments.csv's cause: a carrier or retailer miss owes nothing, and
  discretion can't make it owed, gate.discretion_terms), that it rides on every other fee (add_on: Five Below's $100
  per PO), and bases annual_percent (interest for the line's days) and as_assessed (a fine the other side sets). Two
  schedules for one fee in force from the same day that price it differently ask (row 9); a quantity_variance term
  {pct} makes a quantity fee within it discretion (fees.yaml quantity_codes). fees.yaml governs dates a contract
  version's terms (Five Below 2023 / 2025 by PO date). test_real_contract_accounts.py runs both accounts.
