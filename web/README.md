# Clawback web

Next.js 16 front end for Clawback. Every brand account gets its own workspace: a business overview, the live analysis
of the current payment, approvals, rules, and the tools beside them. Screens display what the API sends; they never
compute money or call an AI model.

## Run it

- Runtime: Node.js 22 (the same as `web/Dockerfile`).
- Package manager: **npm** (`package-lock.json` is the only lockfile).

```bash
cd web
npm ci
npm run dev        # http://localhost:3000 against the API at NEXT_PUBLIC_API_BASE (default http://localhost:8000, `make api`)
npm run dev:mock   # no backend needed: a mock API on :8010 (web/mock/) plus next dev pointed at it
npm run lint
npm run build && npm start
```

`npm run dev:mock` is for working on screens without the backend. It serves the same contract shapes for four
accounts (Peak Bar Co. replays the recorded run in `web/fixtures/`; three more brands get generated runs with
shortage, pricing and spoilage charges). Optional env for it: `MOCK_SPEED` (1 = live-like pacing, 0.2 = fast),
`MOCK_ADMIN_TOKEN`, `MOCK_OWNER_TOKEN` (to try the admin's sign-in and the reset prompt), and
`MOCK_RUNS_PER_VISITOR` (to try the per-visitor limit), and `MOCK_NO_LOOKBACK=1` (the lookback answers 404, so the card hides). The app itself never imports the mock.

## Environment variables

Names only; real values never go in the repo (`.env*` is ignored). Read at **build time** (`NEXT_PUBLIC_*`).

| Name | Example | Meaning |
| --- | --- | --- |
| `NEXT_PUBLIC_API_BASE` | `http://localhost:8000` (default) | Where the API is. `web/Dockerfile` sets `/api` for the deployed domain behind Caddy. |

## Routes

Every route takes `?account=<id>` (the distributor switcher, top right, changes it; links keep it). Without one, the
first account from `GET /accounts` is used.

| Route | What it is |
| --- | --- |
| `/` | Run: send or drop in the payment, watch the agents, answer and approve inline (one admin, the owner), then the result |
| `/charges` | This payment: every charge, the evidence panel and **How Clawback decided** (`&charge=C1` opens one) |
| `/overview` | Six months: KPIs, the current payment, “Before Clawback”, invoiced vs paid vs deducted, deductions by type, remittances, past runs |
| `/saved` | Records: documents, saved rules, the records checks use, the audit log and its chain check |
| `/results` | The scoreboard: totals, QuickBooks posts, the accuracy check |
| `/contracts` `/connections` `/april` `/coach` `/scenario` | The More menu: the signed deal with the agents' terms, where information comes from, next month under saved rules, Deal coach, a pasted clause |
| `/distributors` | Every distributor the supplier sells through, with its plain status |
| `/portal` | The distributor's own portal (its name and colors from the account), opened in a new tab; `&dispute=` picks the dispute |
| `/workspace`, `/home`, `/review`, `/history`, `/audit`, `/upload`, `/board/*` | Old addresses: redirect to the page that has their content now |

## Calls

| Screen action | Call |
| --- | --- |
| Brand menu, every page | `GET /accounts` (cached for the page) |
| Overview | `GET /accounts/{id}/overview`, read again as the run moves (dispute filed, entry posted); `GET /accounts/{id}/lookback` for “Before Clawback” (a 404 hides the card) |
| Download dispute packet | `GET /portal/disputes/{id}/packet.pdf` (a link, opened in a new tab) |
| Open or reload | `GET /runs/latest?account=` (404 = no payment yet), then `GET /runs/{id}/events` (SSE, resumes with `Last-Event-ID` / `?after=`). Never starts a run. |
| “<Distributor> pays” | `POST /payments/{account}`, once per click; with Nessie the run id may be null, then `GET /runs/latest?account=` is polled |
| Evidence panel | `GET /charges/{id}?run_id=`; a clicked number not in its list: `GET /evidence/{id}?run_id=` |
| How Clawback decided | `GET /runs/{id}/trace?charge_id=` and `GET /runs/{id}/trace/summary` |
| Owner's answer | `POST /questions/{id}/answer` `{text, save_rule}` with `X-Clawback-Role-Token` (the admin's access code) |
| Owner's yes or no | `POST /approvals/{id}` `{approve, note, auto_post}` with `X-Clawback-Role-Token` (the admin's access code) |
| Reset workspace | `POST /demo/reset`; a 401 asks for the admin token and retries with `Authorization: Bearer` |
| Portal | `GET /portal/disputes/{id}`, `/messages`, `/portal/presets?account=&dispute_id=`; `POST …/messages` |
| Next month · Coach · Try a clause | `POST /replay/april?account=` · `POST /coach?account=` · `GET /scenario/examples`, `POST /scenario` |
| Results · Audit | `GET /eval/latest` · `GET /audit?account=`, `GET /audit/verify` |

**Sign-in.** One person decides: the owner, signed in as the admin. “Sign in as admin” (brand menu) asks for the
access code once and keeps it for the browser tab (sessionStorage). A local API has no codes, so it can be left
empty. Answering or approving before signing in opens the sign-in first; a 401 asks again (“Only the admin can do
this”). Answers carry “Save as a rule for next time” (on by default); approvals carry “Post fair charges like these
automatically from now on” (off by default).

**Limits.** A 429 from a payment, a next-month run, the coach, a pasted clause or a portal reply shows the API's own
words (“That's the limit for now…”), not an error, with “Use admin token”. Once the presenter enters the admin token
it is sent as `Authorization: Bearer` on those calls and on resets for the rest of the tab.

A step shows as done only when its event arrives from the stream, never because a button was clicked.

## Layout

```
app/(workspace)/   layout, base.css (Tailwind + v0 tokens), workspace.css (the v0 styles), app.css (multi-account additions)
app/(portal)/      the distributor portal, its own layout and portal.css (colors from the account)
components/shell/  AppShell (brand menu, navigation, sign-in, reset), SessionDialogs, ShellFallback
app/(console)/      Run (/) and Distributors: console.css, flow.css, the RunProvider
components/flow/   the run: start, agent strip, stage, matrix, result
components/workspace/  clawback-app (Charges, Overview), charge-workspace (charges, evidence panel), decision-trace,
                   charts (SVG, no library), evidence-parts
components/tools/  ToolFrame + Records, Results, Next month, Deal coach, Try a clause
lib/api.ts         every API call; lib/accounts.ts (account from the URL, code labels); lib/session.ts (roles, prompts)
lib/useRunEvents.ts  event reducer + live stream per account; lib/workspace.ts (wording only, no money math)
mock/              dev-only mock API (npm run dev:mock)
```

`web/fixtures/` holds recorded runs the API's tests and Dockerfile read (written by `python -m api.stubs.fixtures`;
do not hand-edit). The web app doesn't import them; the mock replays them.

## Phone

Every screen works at 375 px with no horizontal scroll; tap targets are at least 44 px there. Wide tables (deliveries,
price lists, remittances) scroll inside their own box.
