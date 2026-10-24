# Clawback web

Next.js 16 front end for Clawback. The workspace screens (Overview, Payments, Approvals, Rules) come from the v0 export Rishi approved; they display events from `api/contracts.py` and never compute money or call an AI model.

## Run it

- Runtime: Node.js 22 (the same as `web/Dockerfile`).
- Package manager: **npm** (`package-lock.json` is the only lockfile; the v0 export's pnpm files were not carried over).

```bash
cd web
npm ci            # or npm install
npm run dev       # http://localhost:3000, fixture mode, no keys and no backend needed
npm run lint
npm run build && npm start
```

| Route | What it is |
| --- | --- |
| `/` | The workspace: Overview, Payments (filters, evidence panel), Approvals, Rules. Navigation is in-page state, not URLs. |
| `/board/demo` | The earlier review board (before the v0 screens), kept working on the recorded run. It has its own root layout and styles. |

## Environment variables

Names only; real values never go in the repo (`.env*` is ignored). Both are read at **build time** (`NEXT_PUBLIC_*`), so restart `npm run dev` after changing them.

| Name | Example | Meaning |
| --- | --- | --- |
| `NEXT_PUBLIC_DATA_SOURCE` | `fixture` (default) or `live` | `fixture` replays `web/fixtures/`. `live` starts a run on the API and follows its event stream. |
| `NEXT_PUBLIC_API_BASE` | `http://localhost:8000` (default) | Where the API is. `web/Dockerfile` sets `/api` for the deployed domain behind Caddy. Only used when `live`. |

Put them in `web/.env.local`, for example:

```
NEXT_PUBLIC_DATA_SOURCE=live
NEXT_PUBLIC_API_BASE=http://localhost:8000
```

## Fixtures versus live

**Fixture mode (default).** `lib/useRunEvents.ts` replays `fixtures/run-events.json` and stops where a person has to act: the owner's answer, then the controller's reply. "Confirm rule as Dana Okafor" plays the recorded answer; Approve plays `run-events.json` to the end; Refuse plays `refusal-events.json`. The sidebar says "Fixture data · no backend". Nothing leaves the browser: no dispute is filed, no message is sent, and the approval says "Simulated posted".

**Live mode.** The same screens, fed by the API:

| Screen action | Call |
| --- | --- |
| Open or refresh the app | `GET /runs/latest` (404 = no run yet), then `GET /runs/{id}/events` (SSE; resumes with `Last-Event-ID` / `?after=`). Never starts a run. |
| "Northmart pays" | `POST /payments/northmart`, then follow the run it started (the only thing that starts a run) |
| Evidence panel | `GET /charges/{id}?run_id=` |
| Confirm rule | `POST /questions/{id}/answer` with the text "accept if notice is at least 14 days" |
| Approve or refuse | `POST /approvals/{id}` with `{approve, note}` |
| Reset fictional demo | `POST /demo/reset`, then wait for "Northmart pays" |

In live mode a step shows as done only when its event arrives from the stream, never because a button was clicked. Local API: `make api` (port 8000). The API's CORS list allows only `http://localhost:3000` and `PUBLIC_BASE_URL`, so run live mode locally on port 3000.

Always labelled as demo data, in both modes: the people (Dana Okafor, Sam Reyes), the brand, the deal text and the evidence excerpts. The "Demo role" switch in the Peak Bar Co. menu is a presentation control only (no authentication); it just decides which of the two buttons is enabled.

## What the screens show, and where it comes from

- Invoiced, received, deducted: the `run` event's remittance.
- Disputed, accepted, waiting: the latest `totals` event. C1 stays one split charge ($1,800 charged, $1,200 accepted, $600 disputed) from its `decision` event.
- Before the owner answers: $4,120 / $1,530 / $1,200. After: $4,120 / $2,730 / $0.
- Disputed money is shown as "Being challenged · Not recovered". "Disputes proposed · Not filed" is shown unless the stream carries a filed dispute in live mode.
- The owner's policy (Rules) and the controller's accounting approval (Approvals) are separate steps with separate buttons.
- The only arithmetic in the front end is `share()` in `lib/format.ts`, for bar widths.

## Layout

```
app/(workspace)/   layout (Manrope), base.css (Tailwind + v0 tokens), workspace.css (the v0 styles, unchanged)
app/(board)/       the earlier board, with its own root layout and globals.css
components/workspace/   clawback-app.tsx (screens), charge-workspace.tsx (charge list, evidence panel)
lib/useRunEvents.ts     event reducer + fixture replay + live stream
lib/workspace.ts        turns events into what the screens show (wording only, no money math)
lib/live.ts             the API calls above
lib/fixture.ts, fixtures/   recorded runs (written by `python -m api.stubs.fixtures`; do not hand-edit)
```

## Known limitations and backend needs

- Fixture mode replays one recording. The owner's reply is the recorded one, and a refusal shows the recorded note from `refusal-events.json`, not what you typed (nothing is sent). Live mode sends your note to `POST /approvals/{id}` and shows what the API recorded.
- A failed or held QuickBooks post is shown with the API's note. Not in the workspace yet: April replay, Deal Coach, Scenario box, Audit log, Northmart portal, `/results` (the API has routes for them; the screens are separate cards R4 to R6).
- `/board/<run id>` follows that run in live mode; `/board/demo` follows the latest one.
- On Windows the API's live pipeline fails at `api/evidence.py` (`%-d` in `strftime` works on Linux and macOS only). Needs Devank; use WSL, Docker, or fixture mode until then.
- Evidence text is the recorded excerpt. Ledger posts from the fixture have no QuickBooks id, so they are labelled "Simulated posted".
