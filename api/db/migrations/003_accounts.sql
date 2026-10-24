-- Accounts (api/accounts.py): every seeded row and every saved event names the account it belongs to, and each data
-- table's key includes it, so two accounts may both have a charge C1, a promo SPRING-26 or a product called Original.
-- Document ids, remittance ids (from invoice ids) and run ids are unique across accounts, so their keys stay.
-- Rows already there are Peak Bar's (the only account before this file). Charges get line_ref (shortage, price and
-- spoilage charges name a delivery line). Safe to run again.

ALTER TABLE documents      ADD COLUMN IF NOT EXISTS account_id text NOT NULL DEFAULT 'peak-bar';
ALTER TABLE remittances    ADD COLUMN IF NOT EXISTS account_id text NOT NULL DEFAULT 'peak-bar';
ALTER TABLE charges        ADD COLUMN IF NOT EXISTS account_id text NOT NULL DEFAULT 'peak-bar',
                           ADD COLUMN IF NOT EXISTS line_ref text;
ALTER TABLE prior_payments ADD COLUMN IF NOT EXISTS account_id text NOT NULL DEFAULT 'peak-bar';
ALTER TABLE store_sales    ADD COLUMN IF NOT EXISTS account_id text NOT NULL DEFAULT 'peak-bar';
ALTER TABLE promo_plan     ADD COLUMN IF NOT EXISTS account_id text NOT NULL DEFAULT 'peak-bar';
ALTER TABLE events         ADD COLUMN IF NOT EXISTS account_id text NOT NULL DEFAULT 'peak-bar';

-- Before this file charges/ was named northmart-<month>.csv; the seed writes charges/<month>.csv from now on.
UPDATE charges SET source_file = 'charges/' || substring(source_file FROM '^charges/northmart-(.*)$')
WHERE source_file LIKE 'charges/northmart-%.csv';

-- Each data table's primary key gains account_id first (a hypertable's keys must keep week_start, and do).
DO $$
DECLARE
    t text;
    k text;
    pk text;
BEGIN
    FOR t, k IN VALUES ('charges', 'account_id, id'), ('prior_payments', 'account_id, ref'),
                       ('store_sales', 'account_id, week_start, product'), ('promo_plan', 'account_id, promo_id')
    LOOP
        SELECT c.conname INTO pk FROM pg_constraint AS c WHERE c.conrelid = t::regclass AND c.contype = 'p';
        IF pk IS NOT NULL AND NOT EXISTS (
            SELECT 1 FROM pg_constraint AS c JOIN pg_attribute AS a ON a.attrelid = c.conrelid AND a.attnum = ANY (c.conkey)
            WHERE c.conrelid = t::regclass AND c.contype = 'p' AND a.attname = 'account_id') THEN
            EXECUTE format('ALTER TABLE %I DROP CONSTRAINT %I', t, pk);
            pk := NULL;
        END IF;
        IF pk IS NULL THEN
            EXECUTE format('ALTER TABLE %I ADD PRIMARY KEY (%s)', t, k);
        END IF;
    END LOOP;
END $$;

CREATE INDEX IF NOT EXISTS events_account_kind ON events (account_id, type);

-- @timescaledb
-- The continuous aggregate keeps each account's weeks apart: rebuilt once with account_id (001_init.sql made it
-- without), then left alone.

DO $$
BEGIN
    IF to_regclass('promo_units_weekly') IS NOT NULL AND NOT EXISTS (
        SELECT 1 FROM pg_attribute WHERE attrelid = 'promo_units_weekly'::regclass AND attname = 'account_id') THEN
        DROP MATERIALIZED VIEW promo_units_weekly;
    END IF;
END $$;

CREATE MATERIALIZED VIEW IF NOT EXISTS promo_units_weekly
WITH (timescaledb.continuous, timescaledb.materialized_only = false) AS
SELECT account_id,
       time_bucket(INTERVAL '1 day', week_start) AS week_start,
       product,
       max(week_end)    AS week_end,
       sum(promo_units) AS promo_units,
       sum(total_units) AS total_units
FROM store_sales
GROUP BY account_id, time_bucket(INTERVAL '1 day', week_start), product
WITH NO DATA;
