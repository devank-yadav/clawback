"""GET /portal/disputes/{id}/packet.pdf: a dispute as a printable packet for the distributor's deductions desk.

One dispute per packet (a long one runs onto a second page): who it's from and to, the invoice, then each line with
its amount, the deal sentence it quotes, the evidence rows behind it and the engine's math (evidence.math_parts, the
same lines the card shows), then the total and the date to file by. Every number is copied from the dispute, the
evidence and the engine (the total is the dispute's own); this module adds nothing up. fpdf2 writes the PDF.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import date

from fpdf import FPDF
from fpdf.enums import XPos, YPos

from api import accounts
from api.contracts import Dispute, Evidence

# The core PDF fonts are Latin-1: swap what the data writes outside it for a plain equivalent.
_PLAIN = str.maketrans({"−": "-", "–": "-", "—": "-", "‘": "'", "’": "'", "“": '"', "”": '"', "…": "...",
                        "≥": ">=", "≤": "<=", "→": "->", "•": "-", " ": " "})


def _text(value: object) -> str:
    return str(value).translate(_PLAIN).encode("latin-1", "replace").decode("latin-1")


def _usd(amount) -> str:
    return f"${amount:,.2f}"


def _day(d: date | None) -> str:
    return f"{d:%B} {d.day}, {d.year}" if d else "not set"


def _row_text(row: Mapping[str, object]) -> str:
    return " · ".join(f"{k}: {v}" for k, v in row.items() if v not in (None, ""))


def packet_pdf(dispute: Dispute, account: accounts.Account, evidence: Mapping[str, Evidence],
               math: Mapping[str, Sequence[str]], file_by: date | None = None) -> bytes:
    """The packet's bytes. `math` is each charge's math lines; `file_by` is used when the lines carry none."""
    inv, them = account.invoice, account.distributor
    pdf = FPDF(format="letter")
    pdf.set_auto_page_break(auto=True, margin=12)
    pdf.set_margins(14, 12)
    pdf.set_title(_text(f"Dispute {dispute.id}"))
    pdf.set_author(_text(account.brand.name))
    pdf.add_page()

    def line(text: str, size: float = 9, style: str = "", h: float = 4.2) -> None:
        pdf.set_font("Helvetica", style, size)
        pdf.multi_cell(0, h, _text(text), new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    line(f"Dispute {dispute.id}", 16, "B", 8)
    line(f"From {account.brand.name} ({account.brand.owner.name}, owner) to {them.name}, {them.desk_email}", 10)
    line(f"Invoice {inv.id}: ${inv.expected:,.2f} invoiced, ${inv.received:,.2f} paid. "
         f"Status: {dispute.status}" + (f", filed {_day(dispute.filed_at.date())}." if dispute.filed_at else "."), 10)
    deadline = next((ln.file_by for ln in dispute.lines if ln.file_by), file_by)
    line(f"File by: {_day(deadline)}", 10, "B")
    pdf.ln(2)

    shown: dict[str, int] = {}  # evidence id -> the line that printed its rows
    for n, ln in enumerate(dispute.lines, 1):
        line(f"{n}. {ln.ref} (charge {ln.charge_id}): {_usd(ln.amount)} disputed", 11, "B", 6)
        line(ln.reason)
        if ln.quote:
            line(f"{ln.clause_ref or 'The deal'}: \"{ln.quote}\"", 9, "I")
        for ev_id in ln.evidence_ids:
            ev = evidence.get(ev_id)
            if ev is None or ev.kind == "clause":  # the clause is quoted above
                continue
            if ev_id in shown:  # a row the packet already printed (the cap line cites every week's sales)
                line(f"- {ev.label}: rows under line {shown[ev_id]}.", 8)
                continue
            line(f"- {ev.label}: {ev.summary}", 8)
            if ev.kind != "charge":  # the charge row is the line itself
                shown[ev_id] = n
                for row in ev.rows:
                    line(f"    {_row_text(row)}", 7, h=3.4)
        line(f"Math: {' '.join(math.get(ln.charge_id) or [ln.math])}", 8.5)
        pdf.ln(1.5)

    total = dispute.total
    line(f"Total disputed: {_usd(total)} on {len(dispute.lines)} line{'' if len(dispute.lines) == 1 else 's'}.",
         11, "B", 6)
    line(f"Please credit {_usd(total)} against invoice {inv.id} or reply with the signed document that allows "
         "these charges.", 9)
    return bytes(pdf.output())
