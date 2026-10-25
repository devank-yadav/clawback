"""Accounts (api/accounts.py): GET /accounts lists them, GET /accounts/{id}/overview is one account's last six
months and its current payment (api/overview.py, computed by code from history/ and the current run), GET
/accounts/{id}/lookback its past deductions checked by the engine (api/lookback.py)."""

from fastapi import APIRouter, HTTPException

from api import accounts, history, library, lookback as lookback_mod, overview as overview_mod, suppliers
from api.contracts import (
    AccountListItem, AccountOverview, Connection, ContractLibrary, DocumentText, Lookback, RunSummary, SavedDocument, SavedOverview, SavedRecords,
)
from api.routes.runs import account_or_404, latest_run_id

router = APIRouter(tags=["accounts"])


def _item(a: accounts.Account) -> AccountListItem:
    return AccountListItem(id=a.id, brand=a.brand, distributor=a.distributor, invoice=a.invoice,
                           latest_run_id=latest_run_id(a), supplier=suppliers.supplier_of(a))


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


@router.get("/accounts/{account_id}/runs", response_model=list[RunSummary])
def account_runs(account_id: str) -> list[RunSummary]:
    """This distributor's runs of the agents, newest first, each summed up from its own events."""
    return history.runs(account_or_404(account_id))


def _title(doc) -> str:
    stem = doc.id.replace("-", " ")
    return {"deal": "Signed deal", "amendment": "Signed amendment", "email": "Email", "notice": "Notice",
            "draft": "Next deal (draft)"}.get(doc.kind, "Document") + f" · {stem}"


def _locked(doc) -> bool:
    return doc.kind in ("deal", "amendment") or doc.signed_by_both


@router.get("/accounts/{account_id}/saved", response_model=SavedOverview)
def account_saved(account_id: str) -> SavedOverview:
    """What Clawback keeps for this distributor: the documents the agents read (signed ones locked), the rules you
    saved, and the records the checks use. Counts only; the records stay where they came from."""
    from api import account_rows, documents, pipeline, rows

    a = account_or_404(account_id)
    docs = []
    with accounts.using(a):
        for doc_id in a.docs:
            try:
                doc, text = documents.load(doc_id)
            except Exception:  # noqa: BLE001 - a file that can't be read isn't listed
                continue
            docs.append(SavedDocument(id=doc.id, kind=doc.kind, title=_title(doc), sender=doc.sender,
                                      locked=_locked(doc), chars=len(text)))
    records = [
        SavedRecords(label="Store sales", rows=len(rows.sales(account=a))),
        SavedRecords(label="Past payments", rows=len(rows.prior_payments(account=a))),
        SavedRecords(label="Promo plan", rows=len(rows.promo_plan(account=a))),
        SavedRecords(label="Deliveries", rows=len(account_rows.deliveries(a))),
        SavedRecords(label="Price list", rows=len(account_rows.price_list(a))),
        SavedRecords(label="Past deductions", rows=len(account_rows.deductions(a))),
    ]
    return SavedOverview(documents=sorted(docs, key=lambda d: (not d.locked, d.kind, d.id)),
                         rules=pipeline.rules_of(a), records=[r for r in records if r.rows])


@router.get("/accounts/{account_id}/documents/{doc_id}", response_model=DocumentText)
def account_document(account_id: str, doc_id: str) -> DocumentText:
    """One document's text, read-only (there is no route that edits a document)."""
    from api import documents

    a = account_or_404(account_id)
    if doc_id not in a.docs:
        raise HTTPException(404, f"{doc_id} isn't one of {a.id}'s documents")
    with accounts.using(a):
        doc, text = documents.load(doc_id)
    return DocumentText(id=doc.id, title=_title(doc), kind=doc.kind, locked=_locked(doc), text=text)


@router.get("/connections", response_model=list[Connection])
def list_connections() -> list[Connection]:
    """Where payments, records and contracts come from, as they really are on this server."""
    return library.connections()


@router.get("/accounts/{account_id}/contract", response_model=ContractLibrary)
def account_contract(account_id: str) -> ContractLibrary:
    """The deal and what changes it, with the terms the agents read in the latest run highlighted. Read-only."""
    return library.library(account_or_404(account_id))
