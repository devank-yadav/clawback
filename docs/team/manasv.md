# Clawback: Manasv's guide

## Your role in 30 seconds

**You run jobs that an AI does for you: paste the prompt, check the result with the given check, commit, move on.** Devank owns the AI agents and the money logic; Rishi owns the screens and every job that needs a human.

- **What we're building:** Clawback, a finance agent for small food brands. A distributor (fictional Northmart) takes $6,850 out of a $48,200 payment; Clawback checks each charge against the deal, disputes $4,120 with proof, accepts $2,730 as fair, and asks the owner one question. Main prize: Hyphenate.
- **You own:** `data/` (including `data/eval/`, the test set and answer key), `scripts/` (small integration scripts), Figma screens, README, Devpost text, captions, judge flashcards, the Fetch.ai chat agent (stretch).
- **Don't touch:** `api/engine/`, `api/agents/`, `config/policy.yaml`, `web/`.
- **The one rule that matters:** every number in `data/` must match `data/CLAUDE.md` to the cent. Your check script proves it.
- **Ask Devank:** anything about how a charge should be decided.
- **Your only human steps:** sign in to Figma, run each script once with the keys, tap "yes" on the controller SMS in the demo, and run `make reset` at the judging table.

## Setup on your laptop

About 10 minutes. The repo is pushed and your invite is accepted; your issues are #11–21.

1. Clone and switch to your branch (it already exists):

```bash
git clone https://github.com/devank-yadav/clawback.git && cd clawback
git checkout story
git pull origin main   # at the start of each session, to pick up Devank's latest
```

2. Install Claude Code if you don't have it (`npm install -g @anthropic-ai/claude-code`) and sign in with your own Claude account.
3. Check `git config user.name` is you; commits carry no AI co-author lines (the repo's settings already turn them off).
4. Sign in to Figma with the free Education plan (for job 4).
5. Start Claude Code in the repo (`claude`) and paste job 1's prompt below.
6. Keys for the scripts come from Devank as a `.env` file; never commit it or paste keys into chat.

## Your jobs

One Claude Code session per job (start fresh with `/clear` between jobs). Paste the prompt, run the check, commit, tell the group chat it's done.

| # | Job | Tool | Prompt to paste | Your check | By |
| --- | --- | --- | --- | --- | --- |
| 1 | All demo data files | Claude Code | "I'm Manasv. Read data/CLAUDE.md. Write every file it lists in data/ (except eval/ and fixtures/) with the exact numbers and wording, plus scripts/check_data.py that asserts every number and total in data/CLAUDE.md." | `python scripts/check_data.py` prints all checks passed | Sat 1 AM |
| 2 | 30-case test set + answer key | Claude Code | "Read data/CLAUDE.md (eval section) and the 'Proof, tests and responsible design' section of docs/design.md. Write data/eval/charges-30.csv and data/eval/answer-key.csv (12 dispute, 12 accept, 6 ask), plus scripts/check_eval.py that verifies the counts and that every case has expected amounts." | `python scripts/check_eval.py` passes; send Devank the file to skim | Sat 1 AM |
| 3 | Integration scripts | Claude Code | "Read scripts/CLAUDE.md and the Setup runbook in docs/design.md. Write scripts/send_sms.py, scripts/nessie_deposit.py and scripts/seed_quickbooks.py. Each reads keys from .env, does one thing, prints the result, and fails with a clear message if a key is missing." | Run each once with the `.env` from Devank; paste the outputs in the group chat | Sat 2 AM |
| 4 | Figma screens | Figma Make, then Figma Agent | "Recreate these screens as Figma frames: payment, board, evidence card, Northmart portal, results, Deal Coach," with the prototype link (https://claude.ai/artifact/LQm2ZyZ8d8oQ5fRbh2VmFR) and the tokens from web/CLAUDE.md | Screenshot each step (FigJam, Design, Make, Agent) into `docs/figma/` for the Figma prize | Sat noon |
| 5 | README | Claude Code | "Write README.md from docs/design.md: what Clawback is, how to run it, the architecture, what's real vs simulated, sponsor tools used. Keep the setup section that's already there." | Renders on GitHub | Sat 4 PM |
| 6 | Devpost text | Claude (chat), with docs/design.md attached | "Write the Devpost sections and one paragraph per track in the Track plan, using only facts in this doc. Leave a placeholder for the eval score and the real quotes." | Save as `docs/devpost.md`; Devank approves Sat night | Sat 4 PM |
| 7 | Judge flashcards | Claude (chat) | "Make 15 likely judge questions with 2-line answers from this doc's Judge Q&A and Responsible design sections." | Save as `docs/flashcards.md`; share in the group chat | Sat 4 PM |
| 8 | Pull-request reviews | Claude Code | "Review the open pull request against docs/design.md and list bugs and missing acceptance tests." | Post the list for the author | Each checkpoint |
| 9 | Video captions | Claude (chat) | "Turn the video table in this doc into a narration script and an .srt captions file timed to it." | Hand to Rishi before 9 PM | Sat 8 PM |
| 10 | Fetch.ai chat agent (stretch) | Claude Code | "Read scripts/CLAUDE.md. Following Fetch.ai's hackpack (resources doc linked in docs/design.md), build scripts/fetch_agent.py: an agent registered on Agentverse with the Agent Chat Protocol that calls only GET /summary and answers 'What did Northmart take this month?' in ASI:One." | It answers inside ASI:One | Sat 8 PM, only if Devank says go |
| 11 | Test-set runs | Terminal | `make eval` | Paste the score and misses to Devank | Sat 4 PM and 8 PM |

## Timeline, checkpoints and rules

| When (PDT) | You |
| --- | --- |
| Fri 11:30 PM–1 AM | Jobs 1 and 2 |
| **1 AM checkpoint** | Both check scripts pass |
| 1–2 AM | Job 3 (once Rishi has the keys) |
| 2–6 AM | Sleep |
| Sat 6 AM–noon | Job 4 (Figma) |
| **Noon gate** | Figma screenshots saved |
| Sat noon–4 PM | Jobs 5, 6, 7; job 8 at checkpoints |
| **4 PM checkpoint** | Job 11 (first eval run) |
| Sat 4–9 PM | Job 9; job 10 if Devank says go; job 11 again at 8 PM |
| 9 PM | Run `make reset` between recording takes |
| **10 PM freeze** | Final Devpost draft from job 6 |
| Sun 6–8:30 AM | Paste the final eval score and quotes; **submit Devpost by 8:30** |
| Sun 10:30 AM | At the table: tap "yes" on the controller SMS, run `make reset` between judges, hold the backup video |

**Rules:**

- Work on your `story` branch; Devank merges at each checkpoint.
- Never edit numbers by hand in `data/`; change the prompt and regenerate, then rerun the check.
- Never paste keys anywhere except `.env` on your laptop.
- Writing (README, Devpost, flashcards) uses only facts from `docs/design.md`; no invented stats or quotes.
- Stuck for 45 minutes → tell Devank right away.
