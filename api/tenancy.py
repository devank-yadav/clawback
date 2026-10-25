"""Who is calling, and which supplier's data they may see (Phase B).

`current_supplier` is the FastAPI dependency on every account-data route. It returns a Caller:
- a signed-in user (the session cookie, api/users.py): sees only their supplier's accounts;
- a script holding OWNER_TOKEN (X-Clawback-Role-Token) or the presenter's `Authorization: Bearer
  <CLAWBACK_ADMIN_TOKEN>`: sees every supplier, as before;
- nobody, on a laptop where no one has a password (users.auth_required() is False): sees everything, as before;
- nobody, where sign-in is on: 401.

Ownership: an account, run, charge, evidence, dispute, question or approval of another supplier is a 404, so other
suppliers' ids aren't even revealed. 401 means "sign in"; 404 means "not yours, or not there".
"""

from __future__ import annotations

import hmac
import os
from dataclasses import dataclass

from fastapi import Header, HTTPException, Request

from api import accounts, users


@dataclass(frozen=True)
class Caller:
    user: users.User | None = None
    supplier_id: str | None = None  # None: every supplier (scripts, the presenter, an open laptop)
    via: str = "open"  # session | owner_token | admin_token | open

    @property
    def everything(self) -> bool:
        return self.supplier_id is None


EVERYONE = Caller()


def supplier_of(account: accounts.Account | str | None) -> str:
    a = accounts.resolve(account or accounts.DEFAULT) if not isinstance(account, accounts.Account) else account
    return a.config.supplier or a.id


def _token_caller(role_token: str | None, authorization: str | None) -> Caller | None:
    owner = os.getenv("OWNER_TOKEN")
    if owner and role_token and hmac.compare_digest(role_token, owner):
        return Caller(via="owner_token")
    admin = os.getenv("CLAWBACK_ADMIN_TOKEN")
    if admin and authorization and hmac.compare_digest(authorization, f"Bearer {admin}"):
        return Caller(via="admin_token")
    return None


def caller(request: Request) -> Caller | None:
    """The caller, or None when nobody is signed in and sign-in is on."""
    user = users.user_for(request.cookies.get(users.COOKIE))
    if user:
        return Caller(user=user, supplier_id=user.supplier_id, via="session")
    tokened = _token_caller(request.headers.get("x-clawback-role-token"), request.headers.get("authorization"))
    if tokened:
        return tokened
    return None if users.auth_required() else EVERYONE


def current_supplier(request: Request, x_clawback_role_token: str | None = Header(default=None),
                     authorization: str | None = Header(default=None)) -> Caller:
    """FastAPI dependency (the Header params only document the token paths; caller() reads them)."""
    found = caller(request)
    if found is None:
        raise HTTPException(401, "Sign in to see this (POST /auth/login).")
    return found


def can_see(who: Caller, account: accounts.Account | str | None) -> bool:
    if who.everything:
        return True
    try:
        return supplier_of(account) == who.supplier_id
    except accounts.UnknownAccount:
        return False


def account_or_404(who: Caller, account_id: str) -> accounts.Account:
    try:
        a = accounts.get(account_id)
    except accounts.UnknownAccount:
        raise HTTPException(404, f"unknown account {account_id}") from None
    if not can_see(who, a):
        raise HTTPException(404, f"unknown account {account_id}")
    return a


def run_account_id(run_id: str) -> str | None:
    """A run's account: a live run's, else the events table's (a run from before a restart)."""
    from api import pipeline
    from api.db import events as saved_events

    run = pipeline.RUNS.get(run_id)
    if run:
        return run.account.id
    return saved_events.account_of(run_id)


def can_see_run(who: Caller, run_id: str | None, fixture_account: str = accounts.DEFAULT) -> bool:
    """A run this caller may see. The recorded fake runs (not live, not saved) are Peak Bar's."""
    if who.everything:
        return True
    if not run_id:
        return False
    aid = run_account_id(run_id) or fixture_account
    return can_see(who, aid)


def visible_runs(who: Caller):
    from api import pipeline

    return [r for r in pipeline.RUNS.values() if can_see(who, r.account)]


def supplier_filter(who: Caller):
    """A predicate on accounts for the pipeline's cross-run lists (inbox, owner messages)."""
    return None if who.everything else (lambda a: can_see(who, a))
