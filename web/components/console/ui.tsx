// Small pieces shared by the console screens. Formatting only: amounts arrive from events.

import type { ReactNode } from "react";
import { dollars } from "@/lib/format";
import type { ChargeStatus } from "@/lib/workspace";

/** $1,240.00 drawn Mercury-style: whole dollars, small raised cents. */
export function Money({ value, className = "" }: { value: number; className?: string }) {
  const text = dollars(value);
  const cut = text.lastIndexOf(".");
  return (
    <span className={`cx-money ${className}`}>
      {text.slice(0, cut)}
      <sup>{text.slice(cut)}</sup>
    </span>
  );
}

export function Pill({ tone = "", live = false, children }: { tone?: "accent" | "green" | "amber" | ""; live?: boolean; children: ReactNode }) {
  return <span className={`cx-pill ${tone ? `is-${tone}` : ""} ${live ? "is-live" : ""}`}>{children}</span>;
}

const STATUS: Record<ChargeStatus, { label: string; tone: "accent" | "green" | "amber" | "" }> = {
  Reviewing: { label: "Checking", tone: "" },
  "Split decision": { label: "Split", tone: "accent" },
  Disputed: { label: "Dispute", tone: "accent" },
  Accepted: { label: "Fair", tone: "" },
  "Needs your input": { label: "Ask owner", tone: "amber" },
  "Can’t verify": { label: "Can’t verify", tone: "" },
};

export function StatusPill({ status }: { status: ChargeStatus }) {
  const s = STATUS[status];
  return (
    <Pill tone={s.tone} live={status === "Reviewing"}>
      {s.label}
    </Pill>
  );
}

export function Logo({ size = 22 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <circle cx="12" cy="12" r="9" stroke="#777cff" strokeWidth="1.8" strokeDasharray="44 13" strokeLinecap="round" />
      <circle cx="12" cy="12" r="3" fill="#777cff" />
    </svg>
  );
}

const CHECK = (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <path d="M5 12l5 5 9-10" />
  </svg>
);
const DOTS = (
  <svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
    <circle cx="12" cy="12" r="4" />
  </svg>
);

export function StepDot({ state }: { state: "done" | "waiting" | "person" }) {
  return <span className="cx-step-dot">{state === "done" ? CHECK : DOTS}</span>;
}

export function KindTag({ kind }: { kind: "AI" | "CODE" | "RULE" }) {
  return <span className={`cx-tag ${kind === "CODE" ? "is-code" : kind === "RULE" ? "is-rule" : ""}`}>{kind}</span>;
}

/** Hh:mm:ss in the demo's time zone, from an event timestamp. */
export const clock = (iso: string | null) =>
  iso ? new Date(iso).toLocaleTimeString("en-US", { hour12: false, timeZone: "America/Los_Angeles" }) : "";
