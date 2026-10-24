# web/ (owner: Rishi)

Next.js + Tailwind + Framer Motion. Every screen displays events; it never computes money or calls an AI model.
Visual reference: the clickable prototype https://claude.ai/artifact/LQm2ZyZ8d8oQ5fRbh2VmFR

## Data source
- Until Devank's live stream is ready, replay `web/fixtures/run-events.json` (Devank writes it) with short delays.
- Later: `GET /runs/{id}/events` (server-sent events, reconnect with Last-Event-ID). Keep the fixture as the
  fallback when DEMO_MODE is on.
- `api/contracts.py` is the source of truth for event and object shapes. If it differs from the sketch below,
  follow contracts.py and tell Devank if a screen needs a field that's missing.

Event sketch: `{ id, type, at, data }`, where type is one of
log {text, level} · finding {charge_id, expected, taken, delta, type, finding, evidence_ids, confidence}
· decision {charge_id, decision: dispute|accept|split|ask|skip, disputed, accepted, gate_row, rule_id}
· question {id, to_role, charge_id, text} · answer {question_id, text, rule_id}
· approval {id, kind, amount, status: pending|approved|refused, note} · dispute {id, lines}
· portal_message {dispute_id, from_party, text, attachment_doc_id} · ledger_post {entity, amount, status}
· totals {disputed, accepted, waiting}

## Screens (see docs/team/rishi.md cards R1 to R8)
/ payment · /board (meters, live feed, Dispute/Accept/Ask columns, evidence drawer) · /portal (Northmart theme)
· /results · /april · /coach · /scenario · /audit · /inbox (fallback for SMS questions)

## Design tokens (from the prototype; define as CSS variables with light and dark values)
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
