"""Who may do what on the deployed site, and how often anyone may spend AI credits.

Roles (docs/design.md, "Approvals"): one person, the admin (the brand's owner), answers the questions and approves the
credit memos. With OWNER_TOKEN set (the VM), those in-app actions need it in the `X-Clawback-Role-Token` header.
Unset (laptops, tests): open, as before. Texts need no token: the Twilio webhook already checks the sender's phone
number and Twilio's signature.

Sign-in (Phase B, api/users.py and api/tenancy.py): each supplier's users sign in with an email and password
(config/users.yaml; passwords from DEMO_USER_PASSWORD / DEMO_USER2_PASSWORD, and ADMIN_PASSWORD still works for Peak
Bar's admin under the old ID "admin"). POST /auth/login sets an HttpOnly session cookie; every account-data route then
shows only that supplier's data. With no password set anywhere (laptops), sign-in stays open. Attempts are limited per
visitor (LOGIN_PER_IP, default 10 per 10 minutes).

Limits: a live run spends ~20 AI calls, and the site is public. With CLAWBACK_ADMIN_TOKEN set (the VM), each client
IP may start RUNS_PER_IP runs (default 3) and make AI_PER_IP other AI requests (default 20: scenario box, Deal Coach,
portal replies) per 10 minutes, and the whole site RUNS_PER_HOUR runs (default 30). `Authorization: Bearer
<CLAWBACK_ADMIN_TOKEN>` skips the limits (the presenter). Uvicorn runs with --proxy-headers, so the client IP is the
caller's, not Caddy's.
"""

from __future__ import annotations

import hmac
import os
import threading
import time
from collections import deque

from fastapi import Header, HTTPException, Request

ROLE_ENV = {"owner": "OWNER_TOKEN"}
DEFAULT_USERNAME = "admin"
WINDOW_S = 600
HOUR_S = 3600


def require_role(role: str = "owner"):
    """FastAPI dependency: the caller is the admin. A signed-in user (api/users.py session cookie) is, for their own
    supplier (each route checks the id belongs to it); so is a script holding OWNER_TOKEN. With neither OWNER_TOKEN nor
    any password set (laptops, tests), it's open."""
    env = ROLE_ENV[role]

    def check(request: Request, x_clawback_role_token: str | None = Header(default=None)) -> None:
        from api import users

        if users.user_for(request.cookies.get(users.COOKIE)):
            return
        token = os.getenv(env)
        if token:
            if not hmac.compare_digest(x_clawback_role_token or "", token):
                raise HTTPException(401, "Only the admin can do this. Sign in as the admin.")
            return
        if users.auth_required():
            raise HTTPException(401, "Only the admin can do this. Sign in as the admin.")

    return check


class NotSetUp(Exception):
    """The site guards the admin's actions but has no password to sign in with."""


def login(username: str, password: str):
    """(the user, the admin's access code for the header) when the ID and password match; (None, None) when not.

    The ID is a user's email (config/users.yaml) or an alias (the old "admin" ID, or ADMIN_USERNAME). Raises NotSetUp
    when OWNER_TOKEN guards the site but nobody has a password. With no password anywhere (laptops), any ID signs in:
    as that user if it names one, else as Peak Bar's admin."""
    from api import users

    token = os.getenv(ROLE_ENV["owner"]) or None
    user = users.find(username)
    if not users.auth_required():
        if token:
            raise NotSetUp("Sign-in isn't set up on this server yet (DEMO_USER_PASSWORD, or ADMIN_PASSWORD).")
        return user or users.default_user(), None
    if user is None:
        users.hash_password(password)  # the same work as a real check, so timing doesn't say which IDs exist
        return None, None
    if not users.check_password(user, password):
        return None, None
    return user, token


_hits: dict[tuple[str, str], deque[float]] = {}
_lock = threading.Lock()


def _admin(authorization: str | None) -> bool:
    token = os.getenv("CLAWBACK_ADMIN_TOKEN")
    return bool(token) and hmac.compare_digest(authorization or "", f"Bearer {token}")


def _allow(key: tuple[str, str], limit: int, window: float, now: float) -> bool:
    seen = _hits.setdefault(key, deque())
    while seen and now - seen[0] > window:
        seen.popleft()
    if len(seen) >= limit:
        return False
    seen.append(now)
    return True


def limit(bucket: str):
    """FastAPI dependency: the per-IP (and, for runs, site-wide) limit for this kind of request."""
    per_ip = {"runs": ("RUNS_PER_IP", 3), "ai": ("AI_PER_IP", 20), "login": ("LOGIN_PER_IP", 10)}[bucket]

    def check(request: Request, authorization: str | None = Header(default=None)) -> None:
        if not os.getenv("CLAWBACK_ADMIN_TOKEN") or _admin(authorization):
            return
        ip = request.client.host if request.client else "unknown"
        now = time.monotonic()
        with _lock:
            if not _allow((bucket, ip), int(os.getenv(per_ip[0], per_ip[1])), WINDOW_S, now):
                if bucket == "login":
                    raise HTTPException(429, "Too many sign-in attempts. Try again in a few minutes.")
                raise HTTPException(429, "That's the limit for now: each analysis runs live AI. Try again in a few "
                                         "minutes.")
            if bucket == "runs" and not _allow(("runs", "*"), int(os.getenv("RUNS_PER_HOUR", 30)), HOUR_S, now):
                raise HTTPException(429, "The site has run its hourly share of live analyses. Try again later.")

    return check


def reset() -> None:
    with _lock:
        _hits.clear()
