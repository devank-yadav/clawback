# Figma → Clawback: how the UI was made

Evidence for the Figma track ("Idea to Demo"). Figma file: **Clawback — Product Design**
(https://www.figma.com/design/YbElaaGZp4zzzVqXToNvOw), page **"02 Clawback — dark workspace exploration"**.

## The process

1. **Idea + references.** We wrote one prompt for Figma Make describing the product (agents that check every
   deduction against the signed contract) and attached screenshots of Mercury's dashboard, transactions drawer and
   Payroll intro as the visual reference.
2. **Figma Make designed the UI.** It produced six screens: Intro (3D dot wave), Home, Payment review,
   Agent activity, Owner policy decision, Controller approval. Screenshots: `02-make-*.png`.
3. **Figma Design.** The screens live as frames in the Figma file above, where we reviewed and refined them.
4. **Handoff with the Figma MCP server.** Claude Code read the frames (structure, colors, type) through Figma's
   MCP server and implemented them in `web/` as real components wired to the agents' live event stream.
   Screenshot of that step: `04-mcp-handoff.png` (add).
5. **Beyond Figma.** Figma Make can't render a live 3D animation, so the dot wave was built in code
   (`web/components/console/DotWave.tsx`): a perspective-projected point surface on a canvas, with the six agents
   riding it. Final app screenshots: `05-live-*.png` (add).

## Where the design lives in code

| Figma frame | Route | Component |
| --- | --- | --- |
| Clawback · Intro | `/welcome` | `components/console/Welcome.tsx` + `DotWave.tsx` |
| Clawback · Home | `/home` | `components/console/Home.tsx` |
| Clawback · Payment review | `/review` | `components/console/Review.tsx` |
| Clawback · Owner policy decision | `/review` (the charge waiting on the owner) | `Review.tsx` → `OwnerDecision` |
| Clawback · Agent activity | `/activity?charge=C1` | `components/console/Activity.tsx` |
| Clawback · Controller approval (now the admin's approval) | `/approval` | `components/console/Approval.tsx` |

Colors come straight from the Figma frames (`app/(console)/console.css`); type is Inter, as in the frames.

## What changed from the Figma output

- Figma Make filled the screens with its own sample data. In the app, every charge, amount, finding and
  decision comes from the run's events (fixture replay or the live API); screens never compute money.
- The agent steps ("How we got here") fill in live as each agent's event arrives.
- Home's six-month chart and two extra distributors are labelled example data: the API doesn't track history yet.
