"use client";

import { useCallback, useState, type ReactNode } from "react";
import { Glyph, Pill } from "@/components/board/parts";
import { statusOf } from "@/components/board/ChargeList";
import { money } from "@/lib/format";
import { CHARGES, RULE_1 } from "@/lib/prototype/charges";
import { OWNER_ANSWER, REMITTANCE } from "@/lib/prototype/run";
import type { DecisionData, Evidence, FindingData, MathRow, QuoteSegment } from "@/lib/types";
import type { RunState } from "@/lib/useRunEvents";

type Props = {
  chargeId: string;
  state: RunState;
  onAnswer: (questionId: string) => void;
  headingRef?: React.Ref<HTMLHeadingElement>;
};

const srcId = (chargeId: string, evidenceId: string) => `src-${chargeId}-${evidenceId.replace(/\W/g, "-")}`;

const WHY_TITLE: Record<string, string> = {
  split: "Why it's split",
  dispute: "Why it's disputed",
  accept: "Why it's fair",
  ask: "Why you're being asked",
  skip: "Why it's on hold",
};

export function EvidencePanel({ chargeId, state, onAnswer, headingRef }: Props) {
  const c = CHARGES[chargeId];
  const f = state.findings[chargeId];
  const d = state.decisions[chargeId];
  const question = Object.values(state.questions).find((q) => q.charge_id === chargeId);
  const [active, setActive] = useState<string | null>(null);

  const evidence: Evidence[] = d?.rule_id ? [RULE_1, ...c.evidence] : c.evidence;
  const primary = evidence.find((e) => e.id === c.quoteRef)!;
  const others = evidence.filter((e) => e.id !== c.quoteRef);

  const show = useCallback((ref: string) => {
    setActive(ref);
    const el = document.getElementById(srcId(chargeId, ref.split("#")[0]));
    el?.scrollIntoView({ block: "nearest", behavior: matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth" });
  }, [chargeId]);

  const status = statusOf(d);

  return (
    <article aria-labelledby={`ev-${chargeId}`} className="flex flex-col">
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <h2 id={`ev-${chargeId}`} ref={headingRef} tabIndex={-1} className="flex items-baseline gap-2 font-display text-[22px] font-semibold focus:outline-none">
            <span className="num text-[15px] font-normal text-muted">{chargeId}</span>
            {c.title}
          </h2>
          <p className="mt-0.5 text-[16px] text-muted">
            {c.detail}
            {f && (
              <>
                , <span className="num text-ink">{money(f.taken)}</span> taken from this payment
              </>
            )}
          </p>
        </div>
        <Pill status={status} />
      </header>

      {!d || !f ? (
        <Checking />
      ) : (
        <>
          <p className="mt-5 max-w-[38rem] font-display text-[22px] leading-snug font-semibold tracking-[-0.005em] text-ink sm:text-[24px]">
            {d.rule_id ? "You set Rule #1: accept display fees with at least 14 days' notice. This one gave 20." : c.headline}
          </p>

          <Allocation d={d} f={f} />

          {d.decision === "ask" && question && !question.answer && (
            <div className="mt-6 rounded-xl border border-ask/45 bg-ask-soft p-4">
              <p className="text-[17px]">{question.text}</p>
              <button
                type="button"
                onClick={() => onAnswer(question.id)}
                className="mt-3 rounded-lg bg-accent px-4 py-2.5 text-[16px] font-semibold text-white shadow-sm hover:brightness-110 dark:text-[#0f151c]"
              >
                {OWNER_ANSWER}
              </button>
            </div>
          )}

          <Section title="What the deal says" id="deal">
            <div id={srcId(chargeId, primary.id)} className="scroll-mt-24">
              <SourceBody e={primary} active={active} large />
              <p className="mt-2 text-[14px] text-muted">{primary.label}</p>
            </div>
          </Section>

          <Section title="The math" id="math" note="Worked out in code, not by AI. Select a number to see where it comes from.">
            <MathTable rows={c.math} active={active} onPick={show} />
          </Section>

          <Section title={WHY_TITLE[d.decision]} id="why">
            <ul className="space-y-1.5">
              {(d.rule_id ? ["Rule #1 matches this fee and this distributor", "Notice was 20 days, more than the 14 you asked for"] : c.checks).map((t) => (
                <li key={t} className="flex gap-2.5 text-[16px]">
                  <svg viewBox="0 0 16 16" width={16} height={16} className="mt-[4px] shrink-0" aria-hidden>
                    <path d="M3.5 8.4 6.6 11.3 12.5 4.8" fill="none" stroke="var(--good)" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
                  </svg>
                  {t}
                </li>
              ))}
            </ul>
            <p className="mt-3 text-[15px] text-muted">{d.rule_id ? `Applied Rule #1, learned Oct 24, approved by ${REMITTANCE.owner}.` : c.gateNote}</p>
          </Section>

          {"pushback" in c.comeback ? (
            <Section title="Ready for their pushback" id="comeback">
              <div className="rounded-xl border border-line bg-sunk p-4">
                <p className="text-[16px] text-muted">Northmart may say</p>
                <p className="mt-0.5 text-[17px]">{c.comeback.pushback}</p>
                <p className="mt-3 text-[16px] text-muted">Clawback answers</p>
                <p className="mt-0.5 text-[17px]">{c.comeback.answer}</p>
              </div>
            </Section>
          ) : (
            <Section title="Pushback" id="comeback">
              <p className="text-[16px] text-muted">{d.rule_id ? "Nothing to rehearse. The charge is fair under your rule." : c.comeback.none}</p>
            </Section>
          )}

          <Section title="Sources" id="sources">
            <ul className="grid gap-2">
              {others.map((e) => (
                <li
                  key={e.id}
                  id={srcId(chargeId, e.id)}
                  className={`scroll-mt-24 rounded-xl border p-3.5 transition-colors ${
                    active?.split("#")[0] === e.id ? "border-accent bg-panel ring-1 ring-accent" : "border-line-soft bg-sunk"
                  }`}
                >
                  <p className="text-[14px] font-semibold text-muted">{e.label}</p>
                  <div className="mt-1">
                    <SourceBody e={e} active={active} />
                  </div>
                </li>
              ))}
            </ul>
          </Section>

          <NextSteps d={d} state={state} />
        </>
      )}
    </article>
  );
}

function Section({ title, id, note, children }: { title: string; id: string; note?: string; children: ReactNode }) {
  return (
    <section aria-labelledby={`sec-${id}`} className="mt-8">
      <h3 id={`sec-${id}`} className="font-display text-[15px] font-semibold text-ink">
        {title}
      </h3>
      {note && <p className="mt-0.5 text-[14px] text-muted">{note}</p>}
      <div className="mt-3">{children}</div>
    </section>
  );
}

function Checking() {
  return (
    <div className="mt-6 space-y-3" aria-live="polite">
      <p className="flex items-center gap-2 text-[16px] text-muted">
        <Glyph status="checking" />
        Checking this charge against the deal
      </p>
      <div className="h-6 w-4/5 rounded bg-sunk" />
      <div className="h-6 w-3/5 rounded bg-sunk" />
      <div className="h-24 w-full rounded-xl bg-sunk" />
    </div>
  );
}

/** Where the money from this charge stands. Widths are a display ratio of supplied amounts. */
function Allocation({ d, f }: { d: DecisionData; f: FindingData }) {
  const parts =
    d.decision === "ask" || d.decision === "skip"
      ? [{ key: "hold", amount: f.taken, label: d.decision === "ask" ? "Waiting on your answer" : "On hold", bar: "bg-ask/80", text: "text-ask" }]
      : [
          { key: "fair", amount: d.accepted, label: "Fair, accepted", bar: "bg-accept/55", text: "text-muted" },
          { key: "over", amount: d.disputed, label: d.decision === "split" ? "Took too much, disputed" : "Disputed", bar: "hatch-dispute border border-dispute/60", text: "text-dispute" },
        ].filter((p) => p.amount > 0);

  return (
    <figure className="mt-6" aria-label={`Of ${money(f.taken)} taken: ${parts.map((p) => `${money(p.amount)} ${p.label.toLowerCase()}`).join(", ")}`}>
      <div className="grid gap-1.5" style={{ gridTemplateColumns: parts.map((p) => `${p.amount}fr`).join(" ") }}>
        {parts.map((p) => (
          <div key={p.key} className={`h-10 rounded-lg ${p.bar}`} />
        ))}
        {parts.map((p) => (
          <figcaption key={p.key} className="min-w-0 pt-1">
            <span className="num block text-[20px] text-ink">{money(p.amount)}</span>
            <span className={`block text-[15px] ${p.text}`}>{p.label}</span>
          </figcaption>
        ))}
      </div>
    </figure>
  );
}

function MathTable({ rows, active, onPick }: { rows: MathRow[]; active: string | null; onPick: (ref: string) => void }) {
  return (
    <dl className="divide-y divide-line-soft overflow-hidden rounded-xl border border-line">
      {rows.map((r) => (
        <div
          key={r.label}
          className={`flex flex-col gap-0.5 px-4 py-3 sm:flex-row sm:items-baseline sm:justify-between sm:gap-6 ${
            r.tone === "dispute" ? "bg-dispute-soft/60" : ""
          }`}
        >
          <dt className={`text-[16px] ${r.tone === "dispute" ? "font-semibold text-dispute" : "text-muted"}`}>{r.label}</dt>
          <dd className="num text-[17px] sm:text-right">
            {r.tokens.map((t, i) =>
              typeof t === "string" ? (
                <span key={i} className="font-sans text-[16px] whitespace-pre-wrap text-muted">
                  {t}
                </span>
              ) : (
                <button
                  key={i}
                  type="button"
                  onClick={() => onPick(t.ref)}
                  title="Show where this number comes from"
                  aria-pressed={active === t.ref}
                  className={`num rounded px-0.5 underline decoration-dotted decoration-1 underline-offset-[5px] transition-colors hover:bg-highlight hover:text-highlight-ink ${
                    active === t.ref ? "bg-highlight text-highlight-ink" : r.tone === "dispute" ? "text-dispute decoration-dispute/60" : "text-ink decoration-muted"
                  }`}
                >
                  {t.value}
                </button>
              ),
            )}
          </dd>
        </div>
      ))}
    </dl>
  );
}

function Quote({ id, segments, active, large }: { id: string; segments: QuoteSegment[]; active: string | null; large?: boolean }) {
  return (
    <blockquote className={`max-w-[40rem] text-ink ${large ? "text-[19px] leading-[1.6]" : "text-[16px] leading-[1.55]"}`}>
      {segments.map((s, i) =>
        typeof s === "string" ? (
          <span key={i}>{s}</span>
        ) : (
          <mark key={i} className="hl" data-active={active === `${id}#${s.mark}` || undefined}>
            {s.text}
          </mark>
        ),
      )}
    </blockquote>
  );
}

function SourceBody({ e, active, large }: { e: Evidence; active: string | null; large?: boolean }) {
  switch (e.kind) {
    case "deal":
      return <Quote id={e.id} segments={e.segments} active={active} large={large} />;
    case "email":
      return (
        <div>
          <p className="text-[14px] text-muted">From {e.from}</p>
          <div className="mt-1">
            <Quote id={e.id} segments={e.segments} active={active} large={large} />
          </div>
        </div>
      );
    case "row":
      return (
        <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-0.5 text-[15px]">
          {e.fields.map(([k, v]) => (
            <div key={k} className="contents">
              <dt className="text-muted">{k}</dt>
              <dd className={/^[$\d]/.test(v) ? "num text-ink" : "text-ink"}>{v}</dd>
            </div>
          ))}
        </dl>
      );
    case "rule":
      return (
        <div>
          <p className="text-[16px]">{e.text}</p>
          <p className="mt-1 text-[14px] text-muted">{e.meta}</p>
        </div>
      );
    case "calc":
      return <p className="text-[15px]">{e.text}</p>;
  }
}

function NextSteps({ d, state }: { d: DecisionData; state: RunState }) {
  const who = REMITTANCE.controller;
  const filed = state.dispute?.lines.find((l) => l.charge_id === d.charge_id);
  const posted = state.ledger.some((p) => p.entity === "Credit memo" && p.status === "posted");
  const a = state.approval;
  const lines: ReactNode[] = [];

  if (d.disputed > 0) {
    lines.push(
      filed ? (
        <>
          <span className="num">{money(filed.amount)}</span> filed on Northmart&apos;s portal in dispute D-0417.
        </>
      ) : (
        <>Filing the dispute on Northmart&apos;s portal…</>
      ),
    );
  }
  if (d.accepted > 0) {
    const where = posted
      ? "posted to QuickBooks in the credit memo."
      : a?.status === "refused"
        ? `held by ${who}. Nothing posted.`
        : a?.status === "pending"
          ? `in the credit memo waiting on ${who}.`
          : `will go into a credit memo for ${who} to approve.`;
    lines.push(
      <>
        <span className="num">{money(d.accepted)}</span> accepted, {where}
      </>,
    );
  }
  if (d.decision === "ask") lines.push(<>Nothing happens until you answer.</>);

  return (
    <Section title="What happens next" id="next">
      <ul className="space-y-1.5 text-[16px]">
        {lines.map((l, i) => (
          <li key={i}>{l}</li>
        ))}
      </ul>
      <p className="mt-2 text-[14px] text-muted">Clawback never moves money on its own.</p>
    </Section>
  );
}
