# Clawback: Devank's guide (lead + core)

You own the contracts, the four agents, the math engine, the decision gate, the run pipeline, QuickBooks writes,
and every decision and cut. Log decisions in DECISIONS.md as you make them.

## First 30 minutes (repo)
1. Unzip the starter into ~/github/clawback, `git init`, first commit, check `git log -1` has no co-author line.
2. Create a private GitHub repo, push, invite Rishi and Manasv. Share the two guide links (or docs/team/*.md).
3. Copy .env.example to .env; fill keys as Rishi sends them. Give Manasv a .env with only the keys his scripts need.

## Your build order (one feature per Claude Code session; /clear between)
| # | Feature (docs/design.md Feature spec) | Done when | By |
| --- | --- | --- | --- |
| 1 | Contracts: api/contracts.py, stub routes, web/fixtures/run-events.json (full fake run, exact numbers) | Pushed; Rishi can build against it | Midnight |
| 2 | F2 Deal Reader (Claude first) + quote check | 6 spring terms extracted, every quote verified, a fake quote rejected | 1 AM |
| 3 | Tiger Data migrations + F1 seed (with Manasv's data + seed_quickbooks.py) | `make seed` twice cleanly; QuickBooks shows $6,850 open | 3 AM |
| 4 | F3 engine/allowed.py (cloud session writes the unit tests) | Tests reproduce C1 to C6, April, the $540 concession | 3 AM |
| 5 | Gemini second reader + agreement check | A disagreement forces Ask | Sat 9 AM |
| 6 | F4 Investigator, F5 gate, runs + SSE | Board fills live with the right piles | Sat 11 AM |
| 7 | F8 owner question → rule (SMS via Manasv's script) | Rule #1 saved; April decided with 0 questions | Sat noon |
| 8 | F9 Negotiator: rehearse, file D-0417, answer replies, concede on amendment-1 | 4 presets answered; $1,000 conceded | Sat 3 PM |
| 9 | F10 controller approval + QuickBooks credit memo + open balance | "yes" posts, "no" posts nothing | Sat 4 PM |
| 10 | F16 Moss, F13 Deal Coach, F17 untrusted emails, F14 scenario endpoint | Each acceptance test passes | Sat 8 PM |
| 11 | F11 DEMO_MODE record/replay, outbound filter, eval fixes | Full demo runs with Wi-Fi off | Sat 9 PM |

## Cloud sessions ($250 credit): good jobs to send, each returns a pull request
- "Write pytest tests for api/engine/allowed.py that reproduce every number in data/CLAUDE.md."
- "Write web/fixtures/run-events.json from api/contracts.py with the exact scenario numbers."
- "Review the open pull requests against docs/design.md; list bugs and missing acceptance tests."
- Never give a cloud session keys or tasks that call live services.

## At every checkpoint (1 AM, noon, 4 PM, 10 PM)
5 minutes: each person shows what runs → merge branches after `make test` → hand out the next task cards →
ask Claude Code: "Compare the repo against the Feature spec and Track plan; list what's done, what's missing
for the next checkpoint, and any track whose cut rule has triggered."

## Cut list (in order) and never-cut list: see docs/design.md "Team plan".
