"use client";

// Shared parts in billow's design language (styles in app/billow.css). Display only: every amount is passed in from
// the run's events or the API; widths in the money bar are proportions of those amounts, never new money.

import type { ReactNode } from "react";
import { money } from "@/lib/format";
import { useCountUp } from "@/components/flow/parts";

/** The small pill above a headline: where you are, or what just happened. */
export function HeroPill({ children, live = false }: { children: ReactNode; live?: boolean }) {
  return <span className={`bw-pill ${live ? "is-live" : ""}`}>{children}</span>;
}

/** A centered page opening: pill, a two-line headline, a subline, then whatever actions follow. */
export function PageHero({ pill, title, sub, children, align = "center" }: { pill?: ReactNode; title: ReactNode; sub?: ReactNode; children?: ReactNode; align?: "center" | "left" }) {
  return (
    <header className={`bw-hero is-${align}`}>
      {pill}
      <h1 className="display">{title}</h1>
      {sub && <p className="bw-hero-sub">{sub}</p>}
      {children}
    </header>
  );
}

/** An app page's header: a plain title, one line of context when it helps, and the page's actions on the right.
 * App pages read data; the big hero (PageHero) belongs to the public site. */
export function PageHeader({ title, line, actions }: { title: ReactNode; line?: ReactNode; actions?: ReactNode }) {
  return (
    <header className="ph">
      <div className="ph-text">
        <h1>{title}</h1>
        {line && <p>{line}</p>}
      </div>
      {actions && <div className="ph-actions">{actions}</div>}
    </header>
  );
}

/** Billow's two-line section head: the claim, then a muted second line. */
export function SectionHead({ title, muted, aside }: { title: ReactNode; muted?: ReactNode; aside?: ReactNode }) {
  return (
    <div className="bw-section-head">
      <h2>{title}{muted && <span>{muted}</span>}</h2>
      {aside}
    </div>
  );
}

export type Tone = "dispute" | "fair" | "wait";

/** Where an amount went, as one stacked bar with every segment labeled (color is never the only cue). */
export function MoneyBar({ label, parts }: { label: ReactNode; parts: { tone: Tone; label: string; value: number }[] }) {
  const shown = parts.filter((p) => p.value > 0);
  if (shown.length === 0) return null;
  return (
    <figure className="bw-bar" aria-label={typeof label === "string" ? label : undefined}>
      <figcaption>{label}</figcaption>
      <div className="bw-bar-track" aria-hidden="true">
        {shown.map((p) => <i key={p.tone} className={`is-${p.tone}`} style={{ flexGrow: p.value }} />)}
      </div>
      <ul className="bw-bar-legend">
        {shown.map((p) => (
          <li key={p.tone}><i className={`is-${p.tone}`} aria-hidden="true" />{p.label}<b>{money(p.value)}</b></li>
        ))}
      </ul>
    </figure>
  );
}

/** One headline number with its label. Money counts up; anything else shows as given. */
export function StatTile({ label, value, amount, tone, hint }: { label: string; value?: ReactNode; amount?: number; tone?: Tone; hint?: ReactNode }) {
  const counted = useCountUp(amount ?? 0);
  return (
    <div className={`bw-stat ${tone ? `is-${tone}` : ""}`}>
      <span>{label}</span>
      <strong>{amount !== undefined ? money(counted) : value}</strong>
      {hint && <small>{hint}</small>}
    </div>
  );
}

/** An invitation, not an apology: what this space is for, and the one thing to do. */
export function EmptyState({ title, line, action }: { title: string; line: string; action?: ReactNode }) {
  return (
    <div className="bw-empty">
      <strong>{title}</strong>
      <p>{line}</p>
      {action}
    </div>
  );
}
