-- Saved rules and the audit chain outlive a restart (api/db/state.py). A rule names the account whose owner answered;
-- the chain's head hash is kept apart from its rows (one row here), so cutting off the newest rows is caught.
-- Safe to run again.

ALTER TABLE rules ADD COLUMN IF NOT EXISTS account_id text NOT NULL DEFAULT 'peak-bar';

CREATE TABLE IF NOT EXISTS audit_head (
    id   smallint PRIMARY KEY DEFAULT 1 CHECK (id = 1),
    hash text NOT NULL                          -- the newest audit_log row's hash
);
