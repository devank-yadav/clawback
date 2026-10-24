# Clawback: Devank's guide (lead + core)

You own the contracts, the four agents, the math engine, the decision gate, the run pipeline, QuickBooks writes,
and every decision and cut. Log decisions in DECISIONS.md as you make them.

## Status and where you work
- Done: repo https://github.com/devank-yadav/clawback (private), branches main / web / story, Rishi and Manasv
  invited and accepted, issues #1–23 assigned, `.env` created on your laptop.
- **Core work (D1–D11): Claude Code on your laptop** in the clawback folder. It has your `.env`, runs tests,
  and commits as you. After its first commit, check `git log -1` has no co-author or session-link line.
- **Side jobs with no keys: the "Clawback" project in claude.ai/code** (cloud sessions, $250 credit, expires
  Nov 4). Each job comes back as a pull request; review it before merging.
- Don't share the project: it bills to your account. Rishi and Manasv use their own Claude accounts on their branches.
- Keys: fill `.env` as Rishi sends them. Give Manasv a `.env` with only Twilio, Nessie and QuickBooks keys before his job 3.
- Tell Rishi the moment `web/fixtures/run-events.json` is pushed; his board depends on it.

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

## Cloud sessions (the Clawback project, $250 credit): queue
| When | Paste into the project |
| --- | --- |
| Running now | Consistency check of the starter docs and config (opens a pull request with a "Needs Devank" list) |
| Right after D1 is pushed | "Write pytest tests in api/engine/tests/ for api/engine/allowed.py that reproduce every number in data/CLAUDE.md: C1 to C6, April A1/A2, and the $540/$1,000 split after amendment-1. Use the interfaces in api/contracts.py. Tests only; don't implement the engine." |
| Right after D1 | "Check web/fixtures/run-events.json against api/contracts.py and data/CLAUDE.md: every event must validate and the totals must end at $4,120 disputed and $2,730 accepted. Fix any mismatch and add a script that validates it." |
| 1 AM checkpoint | "Review the open pull requests from the web and story branches against docs/design.md and the matching CLAUDE.md files; list bugs, missing acceptance tests, and any file edited outside its owner's area." |
| Sat morning | "Write unit tests for api/engine/gate.py covering every row of the decision-gate table in docs/design.md, one minimal case per row." |

Never give a cloud session keys or tasks that call live services. Every cloud prompt ends with:
"Commits must have no Co-Authored-By, Generated-with or session-link lines."

## At every checkpoint (1 AM, noon, 4 PM, 10 PM)
5 minutes: each person shows what runs → merge branches after `make test` → hand out the next task cards →
ask Claude Code: "Compare the repo against the Feature spec and Track plan; list what's done, what's missing
for the next checkpoint, and any track whose cut rule has triggered."

## Cut list (in order) and never-cut list: see docs/design.md "Team plan".
