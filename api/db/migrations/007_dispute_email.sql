-- Dispute email (api/dispute_email.py): each dispute's email and the replies we sent, the reply-address tokens, every
-- message on a dispute's thread (portal or email) and the supplier's notifications, so threads survive a restart.
-- The disputes themselves are in the events table (their "dispute" events). Safe to run again.

CREATE TABLE IF NOT EXISTS dispute_emails (
    id          text PRIMARY KEY,               -- "EM-<run id>-D-0417", "-R<n>" for a reply
    run_id      text NOT NULL,
    account_id  text NOT NULL,
    dispute_id  text NOT NULL,
    kind        text NOT NULL,                  -- dispute | reply
    status      text NOT NULL,                  -- held | ready | sent | outbox | failed
    message_id  text,                           -- Mailgun's Message-Id once sent
    data        jsonb NOT NULL,                 -- the DisputeEmail (api/contracts.py)
    updated_at  timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS dispute_emails_message_id ON dispute_emails (message_id);
CREATE INDEX IF NOT EXISTS dispute_emails_dispute ON dispute_emails (run_id, dispute_id);

CREATE TABLE IF NOT EXISTS dispute_tokens (
    token       text PRIMARY KEY,               -- the <token> in d-0417+<token>@<INBOUND_EMAIL_DOMAIN>
    run_id      text NOT NULL,
    dispute_id  text NOT NULL,
    account_id  text NOT NULL
);

CREATE TABLE IF NOT EXISTS dispute_messages (
    run_id      text NOT NULL,
    id          text NOT NULL,                  -- "PM-D-0417-3"
    dispute_id  text NOT NULL,
    account_id  text NOT NULL,
    created_at  timestamptz NOT NULL,
    data        jsonb NOT NULL,                 -- the PortalMessage, channel portal or email
    PRIMARY KEY (run_id, id)
);

CREATE TABLE IF NOT EXISTS supplier_notifications (
    id          text PRIMARY KEY,
    account_id  text NOT NULL,
    at          timestamptz NOT NULL,
    data        jsonb NOT NULL
);
CREATE INDEX IF NOT EXISTS supplier_notifications_account ON supplier_notifications (account_id, at);
