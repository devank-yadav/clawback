# web/ (owner: Rishi)

Next.js + Tailwind + Framer Motion. Every screen displays events; it never computes money or calls an AI model.
Visual reference: the clickable prototype https://claude.ai/artifact/LQm2ZyZ8d8oQ5fRbh2VmFR

## Data source
- The app always uses the API (`NEXT_PUBLIC_API_BASE`): `GET /accounts`, `/accounts/{id}/overview`, and per account
  `GET /runs/latest?account=` then `GET /runs/{id}/events` (server-sent events, reconnect with Last-Event-ID).
  DEMO_MODE replays happen on the API side. The account is always in the URL (`?account=`); never hardcode a brand.
- Without the backend: `npm run dev:mock` (web/mock/, dev-only, same shapes). `web/fixtures/` stays because the API's
  tests and its Dockerfile read it; the web app doesn't.
- `api/contracts.py` is the source of truth for event and object shapes. If it differs from the sketch below,
  follow contracts.py and tell Devank if a screen needs a field that's missing.

Event sketch: `{ id, type, at, data }`, where type is one of
log {text, level} · stage {stage: read|check, status, done, total, label, charge_id, items} · finding {charge_id, expected, taken, delta, type, finding, evidence_ids, confidence}
· decision {charge_id, decision: dispute|accept|split|ask|skip, disputed, accepted, gate_row, rule_id}
· question {id, to_role, charge_id, text} · answer {question_id, text, rule_id}
· approval {id, kind, amount, status: pending|approved|refused, note} · dispute {id, lines}
· portal_message {dispute_id, from_party, text, attachment_doc_id} · ledger_post {entity, amount, status}
· totals {disputed, accepted, waiting}

## Screens
One top bar (`components/shell/TopBar.tsx`) with five places, a More menu and the distributor switcher. Each thing
lives in one place; don't add a second screen for something one of these already shows.

| Nav | Route | What it has |
| --- | --- | --- |
| Run | `/` (`app/(console)/page.tsx`, `components/flow/`) | Drop in the payment advice or press "<distributor> pays"; the agent strip, the current stage, the charge × agent matrix and the feed; the owner's question and the controller's approval inline; then the result (piles, dispute, next steps). `?run=latest` or `?run=<id>` opens a run |
| Charges | `/charges` | This payment: totals and every charge with its evidence panel and how it was decided (`&charge=C1` opens one) |
| Overview | `/overview` | Six months: KPIs, this month's payment, "Before Clawback" (claim these now), charts, remittances, past runs |
| Records | `/saved` (`components/tools/RecordsApp.tsx`) | Documents (signed ones locked), saved rules, the records checks use, the audit trail with the chain check |
| Results | `/results` | The scoreboard: totals, QuickBooks posts, the 30-case accuracy check |
| More | `/april` `/coach` `/scenario` | Next month under saved rules, Deal coach, Try a clause; plus the distributor's portal (`/portal`, new tab) |

The switcher lists the supplier's tracked distributors; "All distributors" opens `/distributors`. Old addresses
(`/workspace`, `/home`, `/review`, `/history`, `/audit`, `/upload`, ...) redirect in `next.config.ts`.

## Styles (current visual baseline)
`/` and `/distributors` use `app/(console)/` (console.css tokens, flow.css parts, `RunProvider`). Charges, Overview,
Records and the tools use `app/(workspace)/` (`AppShell`), whose layout loads the same console.css and flow.css and
ends with `unify.css`; workspace.css and app.css keep their structure with every light color mapped to the console
tokens. New screens use the console tokens, never new light colors.

## Design tokens from the first prototype (the earlier board is gone; kept for reference)
- Fonts: Archivo (headings, 600/800), Source Sans 3 (text), JetBrains Mono (every number, tabular figures).
- Light: bg #eef1f4, panel #ffffff, ink #15202b, muted #5b6876, line #d5dbe2, accent #1f4fd1,
  dispute red #c2372f (soft #fbe7e5), accept gray #6b7480 (soft #eceff2), ask amber #b7791f (soft #fcf1dc),
  good green #1d7a46, highlight #fff1a8.
- Dark: bg #0f151c, panel #18212b, ink #e7edf3, muted #9aa7b4, line #2b3744, accent #7aa2ff,
  red #ff7b70 (soft #3a1c1b), gray #a3adb8 (soft #232d38), amber #f2b552 (soft #3a2d14), green #5fd394,
  highlight #5b4e12 with text #fff7cc.
- Motion: cards drop in over 450 ms; meters count up over 600 ms; feed lines fade in. Respect prefers-reduced-motion.

## Rules
- Big type, few words, no finance jargon on screen ("took too much", not "off-invoice allowance").
- Must work on a phone (judges may open the URL). No horizontal scroll.
- Run `npm run lint` and `npm run build` before every commit.
- Don't touch api/, data/, config/.
