-- Clawback schema: every table in docs/design.md "Data model and data files", plus the events table the
-- event stream replays from (docs/design.md, API). Safe to run again: everything is IF NOT EXISTS.
-- Columns follow api/contracts.py, which is the source of truth for allowed values (no CHECK lists here).
-- Money is numeric(12,2) in dollars. Run-scoped tables carry run_id and no foreign keys, because scenario and
-- eval runs use charges and documents that aren't seeded.

-- ---------------------------------------------------------------- seeded from data/ (python -m api.db.seed)

CREATE TABLE IF NOT EXISTS documents (
    id              text PRIMARY KEY,           -- "spring-promo", "broker-2026-03-28"
    kind            text NOT NULL,              -- deal, email, amendment, notice, draft
    path            text NOT NULL,              -- relative to data/
    sender          text,
    approved_sender boolean NOT NULL DEFAULT false,
    signed_by_both  boolean NOT NULL DEFAULT false,
    received_at     timestamptz,
    text            text NOT NULL,              -- never edited; quotes are checked against it
    sha256          text NOT NULL
);

CREATE TABLE IF NOT EXISTS remittances (
    id           text PRIMARY KEY,              -- "REM-INV-3102"
    counterparty text NOT NULL,
    invoice_id   text,
    expected     numeric(12,2) NOT NULL,
    received     numeric(12,2) NOT NULL,
    received_at  timestamptz,                   -- set by the run when the Nessie deposit arrives
    nessie_tx_id text
);

CREATE TABLE IF NOT EXISTS charges (
    id            text PRIMARY KEY,             -- "C1".."C6", "A1".."A2"
    remittance_id text REFERENCES remittances (id),
    ref           text NOT NULL,                -- Northmart's reference, "NM-2229"
    code          text NOT NULL,                -- PA promotional allowance, DF display fee
    description   text NOT NULL,
    product       text,                         -- "Original+Chocolate", "Mint", NULL for fees
    units         integer NOT NULL,
    rate          numeric(12,4) NOT NULL,
    amount        numeric(12,2) NOT NULL,
    period_start  date NOT NULL,
    period_end    date NOT NULL,
    notice_date   date                          -- display fees: when Northmart's written notice came
);

CREATE TABLE IF NOT EXISTS prior_payments (
    ref          text PRIMARY KEY,              -- "NM-2178"
    paid_on      date NOT NULL,
    promo_id     text NOT NULL,
    product      text NOT NULL,
    period_start date NOT NULL,
    period_end   date NOT NULL,
    units        integer NOT NULL,
    amount       numeric(12,2) NOT NULL
);

-- One row per product per reporting week. Weeks aren't all 7 days (week 4 runs Mar 22 to 31), so each row keeps
-- its end date. A hypertable on week_start where TimescaleDB is available (bottom of this file).
CREATE TABLE IF NOT EXISTS store_sales (
    week_start  date NOT NULL,
    week_end    date NOT NULL,
    product     text NOT NULL,
    promo_units integer NOT NULL,
    total_units integer NOT NULL,
    PRIMARY KEY (week_start, product),          -- a hypertable's unique keys must include week_start
    CHECK (week_end >= week_start)
);

CREATE TABLE IF NOT EXISTS promo_plan (
    promo_id text PRIMARY KEY,                  -- "SPRING-26"
    products text[] NOT NULL,
    rate     numeric(12,4) NOT NULL,
    starts   date NOT NULL,
    ends     date NOT NULL,
    cap      integer NOT NULL
);

-- ---------------------------------------------------------------- written by runs (empty after the seed)

CREATE TABLE IF NOT EXISTS terms (
    run_id          text NOT NULL,
    id              text NOT NULL,
    doc_id          text NOT NULL,
    reader          text NOT NULL,              -- claude, gemini, claude-b, merged
    type            text NOT NULL,
    params          jsonb NOT NULL,
    effective_from  date,
    effective_to    date,
    exact_quote     text NOT NULL,
    char_start      integer NOT NULL,
    char_end        integer NOT NULL,
    discretion      boolean NOT NULL DEFAULT false,
    status          text NOT NULL,              -- pending, verified, rejected, disputed
    source_approved boolean NOT NULL DEFAULT true,
    reasons         jsonb NOT NULL DEFAULT '[]',
    PRIMARY KEY (run_id, id)
);

CREATE TABLE IF NOT EXISTS findings (
    run_id         text NOT NULL,
    charge_id      text NOT NULL,
    id             text NOT NULL,               -- "F-C1"
    expected       numeric(12,2) NOT NULL,
    taken          numeric(12,2) NOT NULL,
    delta          numeric(12,2) NOT NULL,
    type           text NOT NULL,
    finding        text NOT NULL,
    evidence_ids   text[] NOT NULL DEFAULT '{}',
    confidence     double precision NOT NULL,
    readers_agree  boolean NOT NULL DEFAULT true,
    open_questions jsonb NOT NULL DEFAULT '[]',
    math           jsonb NOT NULL DEFAULT '[]',
    PRIMARY KEY (run_id, charge_id)
);

-- A charge can be decided more than once in a run (C6: Ask, then Rule #1 accepts it).
CREATE TABLE IF NOT EXISTS decisions (
    id         bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    run_id     text NOT NULL,
    charge_id  text NOT NULL,
    decision   text NOT NULL,                   -- dispute, accept, split, ask, skip
    disputed   numeric(12,2) NOT NULL DEFAULT 0,
    accepted   numeric(12,2) NOT NULL DEFAULT 0,
    waiting    numeric(12,2) NOT NULL DEFAULT 0,
    gate_row   smallint NOT NULL CHECK (gate_row BETWEEN 1 AND 9),
    rule_id    text,
    decided_by text NOT NULL,
    decided_at timestamptz NOT NULL,
    reason     text NOT NULL
);
CREATE INDEX IF NOT EXISTS decisions_run_charge ON decisions (run_id, charge_id);

CREATE TABLE IF NOT EXISTS rules (
    id                 text PRIMARY KEY,        -- "rule-1"
    label              text NOT NULL,           -- "Rule #1"
    pattern_text       text NOT NULL,           -- what Moss matches new clauses against
    term_type          text NOT NULL,
    counterparty       text NOT NULL,
    condition          text NOT NULL,           -- "notice_days >= 14"
    decision           text NOT NULL,
    else_decision      text NOT NULL,
    summary            text NOT NULL,
    approver           text NOT NULL,
    approver_role      text NOT NULL,
    learned_at         timestamptz NOT NULL,
    source_question_id text,
    status             text NOT NULL DEFAULT 'active'
);

CREATE TABLE IF NOT EXISTS questions (
    run_id      text NOT NULL,
    id          text NOT NULL,                  -- "Q-1"
    to_role     text NOT NULL,                  -- owner, controller
    charge_id   text,
    text        text NOT NULL,
    channel     text NOT NULL DEFAULT 'sms',
    sent_at     timestamptz NOT NULL,
    answer      text,
    answered_at timestamptz,
    rule_id     text,
    closed_at   timestamptz,
    PRIMARY KEY (run_id, id)
);

CREATE TABLE IF NOT EXISTS approvals (
    id            text PRIMARY KEY,             -- "AP-<run id>"
    run_id        text NOT NULL,
    kind          text NOT NULL,                -- credit_memo, dispute_over_limit, closed_period
    amount        numeric(12,2) NOT NULL,
    lines         jsonb NOT NULL DEFAULT '[]',
    proposed_by   text NOT NULL,
    approver_role text NOT NULL,
    status        text NOT NULL,                -- pending, approved, refused
    text          text NOT NULL,
    note          text,                         -- the approver's note when they refuse
    requested_at  timestamptz NOT NULL,
    decided_at    timestamptz
);

CREATE TABLE IF NOT EXISTS disputes (
    run_id        text NOT NULL,
    id            text NOT NULL,                -- "D-0417"; each run numbers its own
    remittance_id text NOT NULL,
    counterparty  text NOT NULL,
    lines         jsonb NOT NULL,
    total         numeric(12,2) NOT NULL,
    status        text NOT NULL,
    approved_by   text NOT NULL,                -- policy, owner
    filed_at      timestamptz,
    PRIMARY KEY (run_id, id)
);

CREATE TABLE IF NOT EXISTS portal_messages (
    run_id            text NOT NULL,
    id                text NOT NULL,            -- "PM-D-0417-1"
    dispute_id        text NOT NULL,
    from_party        text NOT NULL,            -- northmart, clawback
    text              text NOT NULL,
    attachment_doc_id text,
    classification    text,
    charge_ids        text[] NOT NULL DEFAULT '{}',
    evidence_ids      text[] NOT NULL DEFAULT '{}',
    created_at        timestamptz NOT NULL,
    PRIMARY KEY (run_id, id)
);

CREATE TABLE IF NOT EXISTS ledger_posts (
    id          text PRIMARY KEY,               -- "LP-<approval id>"
    qbo_entity  text NOT NULL,
    qbo_id      text,
    qbo_url     text,
    amount      numeric(12,2) NOT NULL,
    lines       jsonb NOT NULL DEFAULT '[]',
    status      text NOT NULL,
    approval_id text,
    note        text,
    posted_at   timestamptz
);

-- Append only. `at` is text because the hash covers it as that exact string (api/engine/audit_chain.py).
CREATE TABLE IF NOT EXISTS audit_log (
    id         bigint PRIMARY KEY,
    at         text NOT NULL,
    actor      text NOT NULL,
    action     text NOT NULL,
    object_ref text NOT NULL,
    evidence   jsonb NOT NULL DEFAULT '{}',
    prev_hash  text NOT NULL,
    hash       text NOT NULL
);

-- Every event a run streams, so a refresh replays them (GET /runs/{id}/events with Last-Event-ID).
CREATE TABLE IF NOT EXISTS events (
    run_id text NOT NULL,
    id     integer NOT NULL,
    type   text NOT NULL,
    at     timestamptz NOT NULL,
    data   jsonb NOT NULL,
    PRIMARY KEY (run_id, id)
);

-- @timescaledb
-- Only with the timescaledb extension (Tiger Data). On plain Postgres the seed warns and skips this part.

CREATE EXTENSION IF NOT EXISTS timescaledb;

SELECT create_hypertable('store_sales', by_range('week_start'), if_not_exists => TRUE, migrate_data => TRUE);

-- Promoted units per product per reporting week. The CSV's weeks aren't calendar weeks (week 4 is Mar 22 to 31,
-- the extension starts on a Wednesday), so a '1 week' bucket would relabel or merge them; a 1-day bucket on
-- week_start keeps each reporting week as its own bucket. Continuous aggregates can't hold window functions, so
-- the running total against the cap is a query over this view (CAP_QUERY in api/db/seed.py).
-- materialized_only = false: queries also see rows added since the last refresh.
CREATE MATERIALIZED VIEW IF NOT EXISTS promo_units_weekly
WITH (timescaledb.continuous, timescaledb.materialized_only = false) AS
SELECT time_bucket(INTERVAL '1 day', week_start) AS week_start,
       product,
       max(week_end)    AS week_end,
       sum(promo_units) AS promo_units,
       sum(total_units) AS total_units
FROM store_sales
GROUP BY time_bucket(INTERVAL '1 day', week_start), product
WITH NO DATA;
