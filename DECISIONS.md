# Decisions

One line per decision, written the moment it's made: `date time · decision · who`.

- 2026-10-23 23:30 · Product is Clawback (promo/distributor deductions), main prize Hyphenate · Devank
- 2026-10-23 23:30 · Stack: FastAPI + Next.js + Postgres on Tiger Data; Claude for agents, Gemini as second reader · Devank
- 2026-10-23 23:30 · Cartesia, Bright Data, CRS, Visa, Coinbase, Solana, Factory, Creao, Convex, Spacetime not entered · Devank
- 2026-10-23 23:30 · Test cases live in data/eval/; the runner is eval/run.py · Devank
- 2026-10-24 00:45 · Money is Decimal in Python and a JSON number in dollars on the wire (4120.0 = $4,120.00) · Devank
- 2026-10-24 00:45 · SSE: one `data:` line per event with the whole Event JSON, no `event:` line; ids count up per run; Last-Event-ID resumes · Devank
- 2026-10-24 00:45 · Event types beyond the plan's list: run, charge, rehearsal, rule (board and drawer need them); totals also carry taken, undecided, questions · Devank
- 2026-10-24 00:45 · Confirmed Manasv's §6.1 wording: written approval from Dana or broker Jordan Lee changes the deal (matches policy.yaml) · Devank
- 2026-10-24 00:45 · Eval: "split" counts as a dispute; eval/run.py will accept it and check both amounts · Devank
