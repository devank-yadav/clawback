"""Who may do what on the deployed site, and how often anyone may spend AI credits.

Roles (docs/design.md, "Approvals"): one person, the admin (the brand's owner), answers the questions and approves the
credit memos. With OWNER_TOKEN set (the VM), those in-app actions need it in the `X-Clawback-Role-Token` header.
Unset (laptops, tests): open, as before. Texts need no token: the Twilio webhook already checks the sender's phone
number and Twilio's signature.

Sign-in: the admin signs in with an ID and password (ADMIN_USERNAME, default "admin", and ADMIN_PASSWORD), and
POST /auth/login hands the browser OWNER_TOKEN for the header. With neither OWNER_TOKEN nor ADMIN_PASSWORD set
(laptops), any ID and password sign in. Attempts are limited per visitor (LOGIN_PER_IP, default 10 per 10 minutes).

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
    """FastAPI dependency: the caller must hold this role's token, when the site has one."""
    env = ROLE_ENV[role]

    def check(x_clawback_role_token: str | None = Header(default=None)) -> None:
        token = os.getenv(env)
        if token and not hmac.compare_digest(x_clawback_role_token or "", token):
            raise HTTPException(401, "Only the admin can do this. Sign in as the admin (X-Clawback-Role-Token).")

    return check


class NotSetUp(Exception):
    """The site guards the admin's actions but has no password to sign in with."""


def login(username: str, password: str) -> tuple[bool, str | None]:
    """(signed in, the admin's access code for the header). Raises NotSetUp when the site can't sign anyone in."""
    expected = os.getenv("ADMIN_PASSWORD")
    token = os.getenv(ROLE_ENV["owner"]) or None
    if not expected:
        if token:
            raise NotSetUp("Sign-in isn't set up on this server yet (ADMIN_PASSWORD).")
        return True, None
    name = os.getenv("ADMIN_USERNAME") or DEFAULT_USERNAME
    same_name = hmac.compare_digest(username.strip().lower().encode(), name.lower().encode())
    same_password = hmac.compare_digest(password.encode(), expected.encode())
    return (same_name and same_password), token


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
