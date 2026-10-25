"use client";

// The agents talking, during a run: their own lines from the events already arriving (the deal readers agreeing on a
// term, the Negotiator predicting the distributor's comeback and having its answer ready, the rules deciding a charge),
// newest at the bottom, each sliding in. Every word and figure is from an event; nothing here is computed.

import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import { useRun } from "@/components/console/RunProvider";
import { money } from "@/lib/format";

const VERDICT: Record<string, string> = { dispute: "dispute", accept: "fair", split: "split", ask: "ask you", skip: "skip" };
const cut = (s: string, n = 90) => (s.length > n ? `${s.slice(0, n - 1)}…` : s);

export function AgentTalk() {
  const { state, cast } = useRun();
  const still = useReducedMotion();
  const lines: { id: string; who: string; text: string }[] = [];
  state.stages.docs.forEach((d, i) => {
    if (d.items.length) lines.push({ id: `doc-${i}`, who: "Reader A + Reader B", text: `agree on ${d.label}: ${cut(d.items[0], 70)}` });
  });
  for (const id of state.order) {
    const r = state.rehearsals[id];
    if (r) lines.push({ id: `reh-${id}`, who: "Negotiator", text: `predicts “${cut(r.predicted_rebuttal, 60)}”${r.answered ? ", answer ready" : ""}` });
    const d = state.decisions[id];
    if (d) lines.push({ id: `dec-${id}`, who: "Rules", text: `${id}: ${VERDICT[d.decision] ?? d.decision}${d.disputed ? ` · ${money(d.disputed)} disputed` : ""}${d.accepted ? ` · ${money(d.accepted)} fair` : ""}` });
  }
  const q = Object.values(state.questions).find((x) => !x.answer);
  if (q) lines.push({ id: `q-${q.id}`, who: "Rules", text: `asks ${cast.owner}: ${cut(q.text, 70)}` });
  const shown = lines.slice(-3);
  if (!shown.length) return null;
  return (
    <div className="at" aria-label="The agents talking">
      <AnimatePresence initial={false}>
        {shown.map((l) => (
          <motion.p key={l.id} className="at-line" layout={!still}
            initial={still ? false : { opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} exit={still ? { opacity: 0 } : { opacity: 0, y: -8 }}
            transition={{ duration: 0.25 }}>
            <b>{l.who}</b>{l.text}
          </motion.p>
        ))}
      </AnimatePresence>
    </div>
  );
}
