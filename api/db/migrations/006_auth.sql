-- Sign-in and tenant isolation (api/users.py): suppliers (our customers), their users, which accounts each owns, and
-- sign-in sessions. Passwords are never stored: users hold a scrypt hash and its salt. Sessions hold the sha256 of the
-- cookie's token, never the token. Safe to run again.

CREATE TABLE IF NOT EXISTS suppliers (
    id    text PRIMARY KEY,                    -- "peak-bar"
    name  text NOT NULL                        -- "Peak Bar Co."
);

CREATE TABLE IF NOT EXISTS users (
    id             text PRIMARY KEY,           -- the email, lowercased
    email          text NOT NULL UNIQUE,
    name           text NOT NULL,
    supplier_id    text NOT NULL REFERENCES suppliers (id),
    role           text NOT NULL DEFAULT 'admin',
    phone          text,
    password_salt  bytea,                      -- null: this user can't sign in with a password
    password_hash  bytea                       -- hashlib.scrypt(n=2^14, r=8, p=1, dklen=32)
);

CREATE TABLE IF NOT EXISTS supplier_accounts (
    account_id   text PRIMARY KEY,             -- data/accounts/<id>/; one supplier per account
    supplier_id  text NOT NULL REFERENCES suppliers (id)
);
CREATE INDEX IF NOT EXISTS supplier_accounts_supplier ON supplier_accounts (supplier_id);

CREATE TABLE IF NOT EXISTS sessions (
    token_hash  text PRIMARY KEY,              -- sha256 hex of the cookie's token
    user_id     text NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    created_at  timestamptz NOT NULL DEFAULT now(),
    expires_at  timestamptz NOT NULL
);
CREATE INDEX IF NOT EXISTS sessions_expiry ON sessions (expires_at);
