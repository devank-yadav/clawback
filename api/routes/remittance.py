"""Bring in a remittance advice (api/remittance.py): read and check it, then start a run once the person confirms."""

import asyncio

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import ValidationError

from api import remittance
from api.auth import limit
from api.contracts import StartRunResponse

router = APIRouter(tags=["remittance"])

SAMPLES = remittance.documents.DATA / "samples" / "remittances"
SAMPLE_FILES = {"peak-bar": {"northmart-march-2026.pdf": "application/pdf", "northmart-march-2026.txt": "text/plain",
                              "northmart-march-2026-820.txt": "text/plain"}}  # the last is an EDI 820


def _account(account: str) -> None:
    if not remittance.known(account):
        raise HTTPException(404, f"unknown account {account}")


async def _upload(request: Request) -> tuple[str, str]:
    """The remittance's text and what it came as: a multipart `file` (PDF, .txt or .csv), or JSON {"text": ...}."""
    ctype = request.headers.get("content-type", "")
    try:
        if ctype.startswith("multipart/form-data"):
            form = await request.form()
            upload = form.get("file")
            if upload is not None and not isinstance(upload, str):
                data = await upload.read(remittance.MAX_BYTES + 1)
                return remittance.extract_text(data, upload.filename)
            text = form.get("text")
        else:
            body = await request.json()
            text = body.get("text") if isinstance(body, dict) else None
    except remittance.InputError:
        raise
    except Exception as e:  # noqa: BLE001 - a malformed body is the caller's problem, not a crash
        raise HTTPException(422, f"Send a file (multipart, field 'file') or JSON {{\"text\": ...}} ({type(e).__name__}).")
    if not isinstance(text, str):
        raise HTTPException(422, "Send a file (multipart, field 'file') or JSON {\"text\": ...}.")
    return text, "text"


@router.post("/accounts/{account}/remittance", response_model=remittance.RemittanceRead,
             dependencies=[Depends(limit("ai"))])
async def read_remittance(account: str, request: Request) -> remittance.RemittanceRead:
    """Claude reads the remittance (plain code reads an EDI 820) and code checks every line. Starts nothing: the
    person confirms first."""
    _account(account)
    try:
        text, kind = await _upload(request)
        return await asyncio.to_thread(remittance.read, account, text, kind)
    except remittance.InputError as e:
        raise HTTPException(422, str(e)) from e


@router.post("/accounts/{account}/remittance/run", response_model=StartRunResponse,
             dependencies=[Depends(limit("runs"))])
def run_remittance(account: str, req: remittance.RemittanceRunRequest) -> StartRunResponse:
    """Start a run on the charges a read checked (by its read_id), with the account's documents and data."""
    _account(account)
    try:
        return remittance.run_read(account, req.read_id)
    except KeyError as e:
        raise HTTPException(404, f"no remittance read {req.read_id} for {account}; read it again") from e
    except remittance.CannotRun as e:
        raise HTTPException(409, str(e)) from e
    except remittance.NotWired as e:
        raise HTTPException(501, f"Runs from a remittance aren't wired up yet: {e}") from e
    except ValidationError as e:  # a charge the run rejects
        raise HTTPException(422, str(e)) from e


@router.get("/accounts/{account}/remittance/samples/{name}")
def sample(account: str, name: str) -> FileResponse:
    """The sample remittance for the account (data/samples/remittances/), as the distributor would send it."""
    _account(account)
    media = SAMPLE_FILES.get(account, {}).get(name)
    if media is None:
        raise HTTPException(404, f"no sample {name}")
    return FileResponse(SAMPLES / name, media_type=media, filename=name)
