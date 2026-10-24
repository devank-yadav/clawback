"""Accounts (api/accounts.py): GET /accounts lists them, GET /accounts/{id}/overview is one account's last six
months and its current payment (api/overview.py, computed by code from history/ and the current run), GET
/accounts/{id}/lookback its past deductions checked by the engine (api/lookback.py)."""

from fastapi import APIRouter

from api import accounts, lookback as lookback_mod, overview as overview_mod
from api.contracts import AccountListItem, AccountOverview, Lookback
from api.routes.runs import account_or_404, latest_run_id

router = APIRouter(tags=["accounts"])


def _item(a: accounts.Account) -> AccountListItem:
    return AccountListItem(id=a.id, brand=a.brand, distributor=a.distributor, invoice=a.invoice,
                           latest_run_id=latest_run_id(a))


@router.get("/accounts", response_model=list[AccountListItem])
def list_accounts() -> list[AccountListItem]:
    """Every account, Peak Bar first."""
    return [_item(a) for a in accounts.every()]


@router.get("/accounts/{account_id}/overview", response_model=AccountOverview)
def account_overview(account_id: str) -> AccountOverview:
    a = account_or_404(account_id)
    now = overview_mod.current_run(a)
    return overview_mod.overview(a, _item(a).model_copy(update={"latest_run_id": now.run_id}), now)


@router.get("/accounts/{account_id}/lookback", response_model=Lookback)
def account_lookback(account_id: str) -> Lookback:
    """The six-month window's past deductions through the engine's math, and what can still be claimed."""
    return lookback_mod.lookback(account_or_404(account_id))
