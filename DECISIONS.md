# Decisions

One line per decision, written the moment it's made: `date time · decision · who`.

- 2026-10-23 23:30 · Product is Clawback (promo/distributor deductions), main prize Hyphenate · Devank
- 2026-10-23 23:30 · Stack: FastAPI + Next.js + Postgres on Tiger Data; Claude for agents, Gemini as second reader · Devank
- 2026-10-23 23:30 · Cartesia, Bright Data, CRS, Visa, Coinbase, Solana, Factory, Creao, Convex, Spacetime not entered · Devank
- 2026-10-23 23:30 · Test cases live in data/eval/; the runner is eval/run.py · Devank
- 2026-10-24 00:15 · Deal §6.1 lets an approved rep (Dana or broker Jordan Lee) change terms in writing, so the broker email can cover C3; Devank to confirm · Manasv
- 2026-10-24 00:40 · Eval answer key uses 'split' for disputes where part is allowed (counts as dispute; 4 cases); prior_payment format ref:paid_on:start:end:units:amount · Manasv
- 2026-10-24 00:45 · Money is Decimal in Python and a JSON number in dollars on the wire (4120.0 = $4,120.00) · Devank
- 2026-10-24 00:45 · SSE: one `data:` line per event with the whole Event JSON, no `event:` line; ids count up per run; Last-Event-ID resumes · Devank
- 2026-10-24 00:45 · Event types beyond the plan's list: run, charge, rehearsal, rule (board and drawer need them); totals also carry taken, undecided, questions · Devank
- 2026-10-24 00:45 · Confirmed Manasv's §6.1 wording: written approval from Dana or broker Jordan Lee changes the deal (matches policy.yaml) · Devank
- 2026-10-24 00:45 · Eval: "split" counts as a dispute; eval/run.py will accept it and check both amounts · Devank
- 2026-10-24 01:00 · QBO seed splits INV-3102 into Original 9,000 x $2.40, Chocolate 8,000 x $2.40, Mint 3,700 x $2.00 (= $48,200); payment dated 2026-04-20; Devank to confirm · Manasv
- 2026-10-24 00:58 · $5,000 auto-dispute limit is checked per charge in the gate (row 8) and on the dispute's total at filing time (Negotiator, D8); design.md gate row 7 now reads "up to $5,000" · Devank
- 2026-10-24 01:10 · Deal Reader A is claude-opus-5-5 with structured outputs (messages.parse + strict schema), not tool use: forced tool_choice returns 400 on this model; server-side fallbacks "default" on · Devank
- 2026-10-24 01:10 · Reader `unclear` lines are shown for review, never sent as questions; a charge whose term is missing reaches Ask through the gate, so the demo stays at 1 question · Devank
- 2026-10-24 01:10 · An extension that states only its end date starts the day after the deal's date_range ends (set by code, not the model) · Devank
- 2026-10-24 01:31 · Every agent request is deterministic (no run IDs, stable remittance ID REM-INV-3102) so DEMO_MODE recordings replay; full demo replays offline in about 9 s · Devank
- 2026-10-24 01:31 · Owner answers become rules only for discretion clauses; a charge is asked about at most once per run · Devank
- 2026-10-24 01:31 · Rehearsed answers may use any number the agent was given (prior payments included) and write dates as ranges, since the outbound filter reads "before <date>" as a deadline · Devank
