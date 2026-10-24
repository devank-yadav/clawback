# api/ (owner: Devank; only Devank edits engine/, agents/, contracts.py)

FastAPI + Pydantic + SQLAlchemy on Postgres (Tiger Data). See docs/design.md sections: Agents; Rules engine,
decision gate and approvals; Data model; API, live updates and integrations.

## Build order
1. contracts.py: Pydantic models for Term, Charge, Finding, Decision, Rule, Question, Approval, Dispute,
   PortalMessage, LedgerPost, Event. Stub routes return fixtures. Write web/fixtures/run-events.json (a full
   fake demo run with the exact scenario numbers).
2. agents/reader.py (Claude + Gemini) + quote check → engine/allowed.py + tests → agents/investigator.py →
   engine/gate.py → runs + SSE → questions/rules → agents/negotiator.py → QuickBooks writes + approvals →
   agents/coach.py.

## Hard rules
- Money math only in engine/, with pytest tests reproducing every number in data/CLAUDE.md
  (C1 to C6, April A1/A2, the $540 concession after amendment-1).
- Agents return strict JSON; code checks after every agent (quote found word for word, numbers equal engine
  numbers, evidence IDs exist). Failures route to Ask.
- Only approved senders or documents signed by both parties change a deal (config/policy.yaml).
- No agent posts to QuickBooks. Credit memos over $1,000 need the controller.
- Every outside call: timeout 30 s, one retry, DEMO_MODE fixture fallback. Every action written to audit_log.
