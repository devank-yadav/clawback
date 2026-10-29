"""GET /setup: what a new company still has to do before the agents can work on their own, as Home's checklist.

Five steps, each read from how things really are on this server: a distributor tracked, its signed contract in, the
books (QuickBooks) connected, a way for payments to come in (the bank or the remittance inbox), and an address for the
"checked" emails (api/alerts.py). In DEMO_MODE the books and the bank are simulated: those steps say "demo" and don't
count as left to do, so the demo company isn't nagged about connections it can't make.
"""

from __future__ import annotations

from api import autopilot, digest, inbound_email, library, supplier_overview, tenancy
from api.contracts import SetupChecklist, SetupStep
from api.integrations import replay


def checklist(who: tenancy.Caller) -> SetupChecklist:
    tracked = supplier_overview._tracked(who)
    demo = replay.demo_mode()
    n = len(tracked)
    steps = [SetupStep(id="distributor", title="Add a distributor",
                       detail=f"{n} distributor{'s' if n != 1 else ''} tracked" if n else
                       "Tell Clawback who pays you, so it knows which payments to check",
                       state="done" if n else "todo", href="/distributors")]
    no_deal = [a.distributor.name for a in tracked if not a.config.deal_docs]
    steps.append(SetupStep(id="contract", title="Upload the signed contract",
                           detail=(f"Missing for {', '.join(no_deal)}" if no_deal else
                                   "Every distributor’s contract is in" if tracked else
                                   "The agents check every charge against it"),
                           state="todo" if no_deal or not tracked else "done", href="/contracts"))
    books = library.connections()[0]
    steps.append(SetupStep(id="books", title="Connect QuickBooks",
                           detail="Simulated on this demo server" if demo else books.detail,
                           state="demo" if demo else "done" if books.status == "connected" else "todo",
                           href="/connections"))
    bank = library.connections()[1]
    inbox = inbound_email.configured()
    steps.append(SetupStep(id="payments", title="Choose how payments come in",
                           detail=("On the demo, distributors pay from their portals" if demo else
                                   "Your bank is watched for deposits" if bank.status == "connected" else
                                   "Forward payment slips to your Clawback inbox" if inbox else
                                   "Connect your bank, or forward payment slips by email"),
                           state="demo" if demo else "done" if bank.status == "connected" or inbox else "todo",
                           href="/connections"))
    email = autopilot.get(digest.supplier_of(who)).digest_email
    steps.append(SetupStep(id="alerts", title="Add your email",
                           detail=(f"We email {email} when a payment is checked, and every Monday" if email else
                                   "So we can tell you when a payment is checked and something needs you"),
                           state="done" if email else "todo", href="/settings"))
    return SetupChecklist(steps=steps, left=sum(s.state == "todo" for s in steps))
