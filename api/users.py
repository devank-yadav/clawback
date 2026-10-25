"""Suppliers, their users and sign-in sessions (Phase B: real sign-in with tenant isolation).

A supplier is our customer: one brand workspace tracking many distributor accounts (AccountConfig.supplier, else the
account's own id). Its users sign in with an email and password and see only its accounts.

Where they come from:
- Suppliers: every loaded account's `supplier`, named by its home account's brand (or users.yaml supplier_name).
- Users: config/users.yaml, which holds no passwords. A user's password is the first env var in its password_env
  that is set (DEMO_USER_PASSWORD for Peak Bar's admin, DEMO_USER2_PASSWORD for Lantern Hill's). It is hashed once per
  process with hashlib.scrypt and a random per-user salt, and compared with hmac.compare_digest.
- Sessions: a secrets.token_urlsafe token goes to the browser as an HttpOnly cookie; only its sha256 is kept, with an
  expiry (SESSION_HOURS, default 12).

Without a database (laptops, tests, DEMO_MODE) all of this lives in memory. With DATABASE_URL (migration 006) the
suppliers, users (with their scrypt hashes), supplier_accounts and sessions are written to Postgres too, so a session
survives an API restart; any database error falls back to memory.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import os
import re
import secrets
import threading
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

import yaml

from api import accounts

log = logging.getLogger("clawback.users")

USERS_FILE = Path(__file__).resolve().parents[1] / "config" / "users.yaml"
COOKIE = "clawback_session"
SCRYPT = {"n": 2 ** 14, "r": 8, "p": 1, "dklen": 32}


@dataclass(frozen=True)
class Supplier:
    id: str
    name: str


@dataclass(frozen=True)
class User:
    id: str  # the email, lowercased
    email: str
    name: str
    supplier_id: str
    role: str
    phone: str | None = None
    aliases: tuple[str, ...] = ()
    salt: bytes = field(default=b"", repr=False)
    password_hash: bytes = field(default=b"", repr=False)

    @property
    def can_sign_in(self) -> bool:
        return bool(self.password_hash)


def hash_password(password: str, salt: bytes | None = None) -> tuple[bytes, bytes]:
    salt = salt or secrets.token_bytes(16)
    return salt, hashlib.scrypt(password.encode(), salt=salt, **SCRYPT)


def check_password(user: User, password: str) -> bool:
    if not user.can_sign_in:
        return False
    _, got = hash_password(password, user.salt)
    return hmac.compare_digest(got, user.password_hash)


def _digits(phone: str) -> str:
    d = re.sub(r"\D", "", phone or "")
    return d[1:] if len(d) == 11 and d.startswith("1") else d


# ---- the store: rebuilt when users.yaml's env values or the loaded accounts change

_lock = threading.Lock()
_store: dict | None = None
_key: tuple | None = None


def _config() -> list[dict]:
    try:
        return (yaml.safe_load(USERS_FILE.read_text()) or {}).get("users", [])
    except OSError:
        return []


def _env_key(rows: list[dict]) -> tuple:
    names = sorted({n for r in rows for n in [*(r.get("password_env") or []), r.get("phone_env") or ""] if n})
    return tuple((n, os.getenv(n) or "") for n in names) + (tuple(a.id for a in accounts.every()),)


def _build(rows: list[dict]) -> dict:
    suppliers: dict[str, Supplier] = {}
    owned: dict[str, set[str]] = {}
    for a in accounts.every():
        sid = a.config.supplier or a.id
        owned.setdefault(sid, set()).add(a.id)
        if sid not in suppliers or a.id == sid:  # the supplier's home account names it
            suppliers[sid] = Supplier(sid, a.brand.name)
    users: dict[str, User] = {}
    for r in rows:
        sid = r["supplier"]
        suppliers.setdefault(sid, Supplier(sid, r.get("supplier_name") or sid))
        owned.setdefault(sid, set())
        password = next((os.getenv(n) for n in r.get("password_env") or [] if os.getenv(n)), None)
        salt, digest = hash_password(password) if password else (b"", b"")
        email = r["email"].strip().lower()
        users[email] = User(id=email, email=email, name=r.get("name") or email, supplier_id=sid,
                            role=r.get("role") or "admin", phone=os.getenv(r["phone_env"]) if r.get("phone_env") else None,
                            aliases=tuple(x.lower() for x in r.get("aliases") or []), salt=salt, password_hash=digest)
    return {"suppliers": suppliers, "owned": owned, "users": users}


def _get() -> dict:
    global _store, _key
    rows = _config()
    key = _env_key(rows)
    with _lock:
        if _store is None or key != _key:
            _store, _key = _build(rows), key
            _save_directory(_store)
        return _store


def reset() -> None:
    """Forget the store and every session (tests, POST /demo/reset doesn't call this: sign-ins outlive a reset)."""
    global _store, _key
    with _lock:
        _store, _key = None, None
        _sessions.clear()


def suppliers() -> dict[str, Supplier]:
    return _get()["suppliers"]


def supplier(supplier_id: str) -> Supplier | None:
    return suppliers().get(supplier_id)


def users() -> list[User]:
    return list(_get()["users"].values())


def auth_required() -> bool:
    """Sign-in is enforced once anyone has a password (the VM). A laptop with none stays open."""
    return any(u.can_sign_in for u in users())


def find(login: str) -> User | None:
    """A user by email, or by an alias (the old "admin" ID, or ADMIN_USERNAME)."""
    name = (login or "").strip().lower()
    by_email = _get()["users"]
    if name in by_email:
        return by_email[name]
    legacy = (os.getenv("ADMIN_USERNAME") or "").strip().lower()
    return next((u for u in by_email.values() if name in u.aliases or (legacy and name == legacy and "admin" in u.aliases)),
                None)


def default_user() -> User | None:
    """Who an open laptop signs in as when the ID matches nobody: Peak Bar's admin."""
    return next((u for u in users() if u.supplier_id == accounts.DEFAULT), None) or next(iter(users()), None)


def by_phone(phone: str) -> User | None:
    digits = _digits(phone)
    if not digits:
        return None
    return next((u for u in users() if u.phone and _digits(u.phone) == digits), None)


# ---- sessions

@dataclass(frozen=True)
class Session:
    token_hash: str
    user_id: str
    expires_at: datetime


_sessions: dict[str, Session] = {}


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def session_hours() -> float:
    try:
        return float(os.getenv("SESSION_HOURS") or 12)
    except ValueError:
        return 12.0


def start_session(user: User) -> tuple[str, Session]:
    token = secrets.token_urlsafe(32)
    s = Session(_hash(token), user.id, datetime.now(timezone.utc) + timedelta(hours=session_hours()))
    with _lock:
        _sessions[s.token_hash] = s
    _db_write("INSERT INTO sessions (token_hash, user_id, expires_at) VALUES (%s, %s, %s) "
              "ON CONFLICT (token_hash) DO NOTHING", (s.token_hash, s.user_id, s.expires_at))
    return token, s


def user_for(token: str | None) -> User | None:
    """The signed-in user for a session cookie, or None (no cookie, unknown, expired)."""
    if not token:
        return None
    h = _hash(token)
    with _lock:
        s = _sessions.get(h)
    if s is None:
        row = _db_read("SELECT user_id, expires_at FROM sessions WHERE token_hash = %s", (h,))
        if row:
            s = Session(h, row[0], row[1])
            with _lock:
                _sessions[h] = s
    if s is None:
        return None
    if s.expires_at <= datetime.now(timezone.utc):
        end_session(token)
        return None
    return _get()["users"].get(s.user_id)


def end_session(token: str | None) -> None:
    if not token:
        return
    h = _hash(token)
    with _lock:
        _sessions.pop(h, None)
    _db_write("DELETE FROM sessions WHERE token_hash = %s", (h,))


# ---- Postgres (migration 006), best effort: memory is the source of truth for this process

def _db_write(sql: str, args: tuple) -> None:
    from api.db import conn

    if not conn.enabled():
        return
    try:
        conn.shared.run(lambda db: db.execute(sql, args))
    except Exception as e:  # noqa: BLE001 - sign-in keeps working from memory
        log.warning("users: couldn't write to Postgres (%s)", conn.scrub(e))


def _db_read(sql: str, args: tuple):
    from api.db import conn

    if not conn.enabled():
        return None
    try:
        return conn.shared.run(lambda db: db.execute(sql, args).fetchone())
    except Exception as e:  # noqa: BLE001
        log.warning("users: couldn't read Postgres (%s)", conn.scrub(e))
        return None


def _save_directory(store: dict) -> None:
    """Upsert suppliers, users and supplier_accounts (the hashes this process made; a restart makes new salts)."""
    from api.db import conn

    if not conn.enabled():
        return

    def write(db):
        for s in store["suppliers"].values():
            db.execute("INSERT INTO suppliers (id, name) VALUES (%s, %s) ON CONFLICT (id) DO UPDATE SET name = "
                       "EXCLUDED.name", (s.id, s.name))
        for sid, ids in store["owned"].items():
            for aid in ids:
                db.execute("INSERT INTO supplier_accounts (supplier_id, account_id) VALUES (%s, %s) "
                           "ON CONFLICT (account_id) DO UPDATE SET supplier_id = EXCLUDED.supplier_id", (sid, aid))
        for u in store["users"].values():
            db.execute("INSERT INTO users (id, email, name, supplier_id, role, phone, password_salt, password_hash) "
                       "VALUES (%s, %s, %s, %s, %s, %s, %s, %s) ON CONFLICT (id) DO UPDATE SET name = EXCLUDED.name, "
                       "supplier_id = EXCLUDED.supplier_id, role = EXCLUDED.role, phone = EXCLUDED.phone, "
                       "password_salt = EXCLUDED.password_salt, password_hash = EXCLUDED.password_hash",
                       (u.id, u.email, u.name, u.supplier_id, u.role, u.phone, u.salt or None, u.password_hash or None))

    try:
        conn.shared.run(write)
    except Exception as e:  # noqa: BLE001
        log.warning("users: couldn't save the directory to Postgres (%s)", conn.scrub(e))
