"use client";

import { AnimatePresence, motion } from "framer-motion";
import type { FeedLine } from "@/lib/useRunEvents";

const DOT = { info: "bg-muted", good: "bg-good", warn: "bg-ask", error: "bg-dispute" } as const;

/** Secondary: every step of the run, collapsed under the charges. */
export function ActivityFeed({ feed }: { feed: FeedLine[] }) {
  return (
    <details className="group rounded-xl border border-line-soft bg-panel/60">
      <summary className="flex cursor-pointer list-none items-center justify-between gap-2 rounded-xl px-4 py-3 text-[15px] text-muted hover:text-ink [&::-webkit-details-marker]:hidden">
        <span>
          Activity <span className="num text-[13px]">{feed.length}</span>
        </span>
        <svg viewBox="0 0 16 16" width={14} height={14} className="transition-transform group-open:rotate-180" aria-hidden>
          <path d="m4 6 4 4 4-4" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      </summary>
      <ol className="space-y-2 px-4 pb-4">
        <AnimatePresence initial={false}>
          {feed.map((l) => (
            <motion.li key={l.id} initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ duration: 0.3 }} className="flex gap-2.5 text-[15px]">
              <span className={`mt-[9px] size-1.5 shrink-0 rounded-full ${DOT[l.level]}`} aria-hidden />
              {l.text}
            </motion.li>
          ))}
        </AnimatePresence>
      </ol>
    </details>
  );
}
