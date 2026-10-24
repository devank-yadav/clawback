# Clawback team brief (all three of us)

Cal Hacks 13.0, main prize Hyphenate. Repo: https://github.com/devank-yadav/clawback (private).
Full plan: docs/design.md. Each person's guide: docs/team/devank.md, rishi.md, manasv.md.

## What we're building
Clawback checks every charge a distributor (fictional Northmart) takes out of a small brand's payment (fictional
Peak Bar Co.) against the signed promo deal. It disputes the wrong ones with proof, accepts the fair ones, asks the
owner once when the deal is unclear (then remembers the answer as a rule), and records the result in QuickBooks.
Fixed demo numbers: $48,200 invoiced, $41,350 paid, $6,850 taken, $4,120 disputed, $2,730 accepted, 1 question.

## Who does what
| Person | Branch | Owns | Issues | Works in |
| --- | --- | --- | --- | --- |
| Devank (lead) | main | api/contracts.py, api/engine/, api/agents/, config/policy.yaml, QuickBooks writes, every decision and cut | #22–23 | Claude Code on his laptop; the claude.ai/code "Clawback" project for key-free side jobs |
| Rishi | web | web/ (all screens), sign-ups and keys, deployment, sponsor questions, real quotes, recording | #1–10 | Claude Code on his laptop, his own account |
| Manasv | story | data/, data/eval/, scripts/, Figma screens, README, Devpost text, flashcards | #11–21 | Claude Code on his laptop, his own account |

If a task needs a file outside your area, stop and ask Devank. Blocked for 45 minutes → tell Devank.

## Right now (Fri night)
- Devank: D1, the contracts, stub routes and web/fixtures/run-events.json; push by about 12:30 AM.
- Rishi: sign-ups and keys first (send keys to Devank privately), then R1 (scaffold + payment screen). R2 after the fixture lands.
- Manasv: job 1 (data files + scripts/check_data.py), then job 2 (30-case test set). Both by 1 AM.

## Checkpoints (PDT)
1 AM: fixture pushed, data check passes, keys collected · Sat noon: full loop runs end to end, ugly ·
Sat 4 PM: four demo moments work, first eval score · Sat 10 PM: feature freeze · Sun 8:30 AM: Devpost submitted (locks at 9).
At each checkpoint everyone shows what runs; Devank merges branches into main after `make test`.
Start each session with `git pull origin main`.

## Rules for every Claude session
- Read CLAUDE.md and your own guide first; do one card or job per session (`/clear` between).
- Never change the demo numbers. Money math lives only in api/engine/ with tests.
- Keys live only in `.env` on your laptop: never in the repo, chat, Slack or a cloud session.
- Commits are authored by you, with no Co-Authored-By, "Generated with" or session-link lines.
- Never invent API keys, URLs, package names, stats, quotes or sponsor rules. Check the docs or ask.
- Log decisions in DECISIONS.md (one line: time, decision, who).
