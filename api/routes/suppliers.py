"""GET /suppliers: each supplier workspace with its distributors and their plain statuses (api/suppliers.py).
POST /suppliers/{id}/tracking: track or untrack one of its distributors."""

from fastapi import APIRouter, HTTPException

from api import accounts, suppliers
from api.contracts import SupplierItem, TrackRequest

router = APIRouter(tags=["suppliers"])


@router.get("/suppliers", response_model=list[SupplierItem])
def list_suppliers() -> list[SupplierItem]:
    return suppliers.items()


@router.post("/suppliers/{supplier_id}/tracking", response_model=SupplierItem)
def track(supplier_id: str, req: TrackRequest) -> SupplierItem:
    try:
        a = accounts.get(req.account_id)
    except accounts.UnknownAccount:
        raise HTTPException(404, f"unknown account {req.account_id}") from None
    if suppliers.supplier_of(a) != supplier_id:
        raise HTTPException(404, f"{req.account_id} isn't one of {supplier_id}'s distributors")
    suppliers.set_tracked(supplier_id, a.id, req.tracked)
    return next(s for s in suppliers.items() if s.id == supplier_id)
