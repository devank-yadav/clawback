-- The admin's auto-post limit, one per account (api/db/state.py): fair-charge credit memos up to it post without
-- asking. Set by ticking "Post fair charges like these automatically from now on" when approving a memo. Safe to run
-- again.

CREATE TABLE IF NOT EXISTS auto_post_limits (
    account_id  text PRIMARY KEY,
    limit_usd   numeric(12, 2) NOT NULL,
    set_by      text NOT NULL,                  -- the admin's name
    approval_id text NOT NULL,                  -- the memo approved when it was set
    set_at      timestamptz NOT NULL
);
