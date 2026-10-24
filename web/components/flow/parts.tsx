"use client";

// Small pieces of the agents' flow. Display only: every amount arrives in an event.

import { useEffect, useRef, useState } from "react";
import { Money } from "@/components/console/ui";

export const CHECK = (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <path d="M5 12l5 5 9-10" />
  </svg>
);

const reduced = () => typeof window !== "undefined" && window.matchMedia("(prefers-reduced-motion: reduce)").matches;

/** Counts up to `value` over 600 ms whenever it changes (straight to it with reduced motion). */
export function useCountUp(value: number): number {
  const [shown, setShown] = useState(value);
  const from = useRef(value);
  useEffect(() => {
    const start = from.current;
    if (start === value) return;
    let raf = 0;
    const t0 = performance.now();
    const step = (t: number) => {
      const k = reduced() ? 1 : Math.min(1, (t - t0) / 600);
      const eased = 1 - (1 - k) ** 3;
      setShown(start + (value - start) * eased);
      if (k < 1) raf = requestAnimationFrame(step);
      else from.current = value;
    };
    raf = requestAnimationFrame(step);
    return () => {
      cancelAnimationFrame(raf);
      from.current = value;
    };
  }, [value]);
  return Math.round(shown * 100) / 100;
}

export function Meter({ label, value, tone, hint }: { label: string; value: number; tone: "dispute" | "fair" | "wait"; hint?: string }) {
  const shown = useCountUp(value);
  return (
    <div className={`fl-meter is-${tone}`}>
      <span>{label}</span>
      <Money value={shown} />
      {hint && <span className="cx-tiny">{hint}</span>}
    </div>
  );
}

/** m:ss since `from`, ticking while `running`; once the run is decided it shows the API's own number. */
export function Elapsed({ from, running, decidedIn }: { from: string | null; running: boolean; decidedIn: number | null }) {
  const [now, setNow] = useState<number | null>(null);
  useEffect(() => {
    if (!running || !from) return;
    const tick = () => setNow(Date.now());
    const id = window.setInterval(tick, 1000);
    const first = window.setTimeout(tick, 0);
    return () => {
      window.clearInterval(id);
      window.clearTimeout(first);
    };
  }, [running, from]);
  if (decidedIn !== null) return <span className="fl-clock">Decided in {Math.round(decidedIn)} s</span>;
  if (!from || now === null) return <span className="fl-clock">{running ? "Starting…" : ""}</span>;
  const s = Math.max(0, Math.floor((now - Date.parse(from)) / 1000));
  return (
    <span className="fl-clock">
      <span className="cx-pill is-live">Live</span>
      {Math.floor(s / 60)}:{String(s % 60).padStart(2, "0")} elapsed
    </span>
  );
}

/** The agents' labels in the activity feed (LogLine.actor). */
export const ACTOR: Record<string, string> = {
  system: "Clawback", reader: "Deal readers", investigator: "Investigator", gate: "Rules", negotiator: "Negotiator",
  bookkeeper: "Bookkeeper", coach: "Deal coach", owner: "Admin", policy: "Policy",
  northmart: "Distributor", distributor: "Distributor",
};
