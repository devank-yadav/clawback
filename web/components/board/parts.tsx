"use client";

import { animate, useReducedMotion } from "framer-motion";
import { useEffect, useRef, useState } from "react";
import { money } from "@/lib/format";
import type { DecisionKind } from "@/lib/types";

export type Status = DecisionKind | "checking" | "answered";

export const STATUS_LABEL: Record<Status, string> = {
  dispute: "Disputing",
  split: "Split",
  accept: "Fair",
  ask: "Needs your answer",
  skip: "Can't verify the deal",
  checking: "Checking",
  answered: "Fair",
};

/** Small status mark. Split is drawn half fair, half disputed, so it reads at a glance. */
export function Glyph({ status, className = "" }: { status: Status; className?: string }) {
  const c = `inline-block shrink-0 ${className}`;
  switch (status) {
    case "dispute":
      return (
        <svg viewBox="0 0 16 16" className={c} width={16} height={16} aria-hidden>
          <circle cx="8" cy="8" r="6" fill="var(--dispute)" />
        </svg>
      );
    case "split":
      return (
        <svg viewBox="0 0 16 16" className={c} width={16} height={16} aria-hidden>
          <path d="M8 2a6 6 0 0 1 0 12z" fill="var(--dispute)" />
          <path d="M8 2a6 6 0 0 0 0 12" fill="none" stroke="var(--accept)" strokeWidth="1.6" />
          <path d="M8 2v12" stroke="var(--dispute)" strokeWidth="1.2" />
        </svg>
      );
    case "accept":
    case "answered":
      return (
        <svg viewBox="0 0 16 16" className={c} width={16} height={16} aria-hidden>
          <circle cx="8" cy="8" r="6" fill="none" stroke="var(--accept)" strokeWidth="1.6" />
          <path d="M5.3 8.2 7.2 10l3.5-3.8" fill="none" stroke="var(--accept)" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      );
    case "ask":
      return (
        <svg viewBox="0 0 16 16" className={c} width={16} height={16} aria-hidden>
          <circle cx="8" cy="8" r="6" fill="var(--ask-soft)" stroke="var(--ask)" strokeWidth="1.6" />
          <circle cx="8" cy="8" r="2" fill="var(--ask)" />
        </svg>
      );
    case "skip":
      return (
        <svg viewBox="0 0 16 16" className={c} width={16} height={16} aria-hidden>
          <circle cx="8" cy="8" r="6" fill="none" stroke="var(--muted)" strokeWidth="1.6" strokeDasharray="2 2" />
        </svg>
      );
    case "checking":
      return (
        <svg viewBox="0 0 16 16" className={`${c} motion-safe:animate-spin`} width={16} height={16} aria-hidden>
          <circle cx="8" cy="8" r="6" fill="none" stroke="var(--line)" strokeWidth="1.6" />
          <path d="M8 2a6 6 0 0 1 6 6" fill="none" stroke="var(--muted)" strokeWidth="1.6" strokeLinecap="round" />
        </svg>
      );
  }
}

const PILL_TONE: Record<Status, string> = {
  dispute: "bg-dispute-soft text-dispute",
  split: "bg-dispute-soft text-dispute",
  accept: "bg-accept-soft text-accept",
  answered: "bg-accept-soft text-accept",
  ask: "bg-ask-soft text-ask",
  skip: "bg-accept-soft text-muted",
  checking: "bg-sunk text-muted",
};

export function Pill({ status }: { status: Status }) {
  return (
    <span className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-[14px] font-semibold ${PILL_TONE[status]}`}>
      <Glyph status={status} className="size-3.5" />
      {STATUS_LABEL[status]}
    </span>
  );
}

/** Counts a supplied amount up from its previous value. Display only. */
export function CountUp({ value, className = "" }: { value: number; className?: string }) {
  const reduce = useReducedMotion();
  const [shown, setShown] = useState(value);
  const from = useRef(value);
  useEffect(() => {
    if (reduce) {
      from.current = value;
      // Snap without animating when the viewer asks for less motion.
      const id = requestAnimationFrame(() => setShown(value));
      return () => cancelAnimationFrame(id);
    }
    const controls = animate(from.current, value, {
      duration: 0.6,
      ease: [0.22, 1, 0.36, 1],
      onUpdate: (v) => setShown(Math.round(v)),
    });
    from.current = value;
    return () => controls.stop();
  }, [value, reduce]);
  return (
    <span className={`num ${className}`} aria-label={money(value)}>
      <span aria-hidden>{money(shown)}</span>
    </span>
  );
}

export function PrototypeBadge() {
  return (
    <span
      className="inline-flex shrink-0 items-center gap-1.5 rounded-full border border-dashed whitespace-nowrap border-line px-2.5 py-0.5 text-[13px] text-muted"
      title="Replaying the recorded demo run from web/fixtures. Live data arrives with the API stream."
    >
      <svg viewBox="0 0 16 16" width={12} height={12} aria-hidden>
        <path d="M3 3h10v10H3z" fill="none" stroke="currentColor" strokeWidth="1.5" strokeDasharray="2.2 1.8" />
      </svg>
      Recorded<span className="hidden sm:inline"> run</span>
    </span>
  );
}
