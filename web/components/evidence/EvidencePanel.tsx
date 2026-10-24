"use client";

import { useCallback, useState, type ReactNode } from "react";
import { chargeLine, openQuestionOf, sentence, statusOf } from "@/components/board/ChargeList";
import { Glyph, Pill } from "@/components/board/parts";
import { CAST } from "@/lib/cast";
import { recordedAnswer } from "@/lib/fixture";
import { useChargeDetail } from "@/lib/useChargeDetail";
import { money, rate, shortDate, shortDay, units } from "@/lib/format";
import type { Decision, Evidence, MathPart, Quote } from "@/lib/types";
import { DATA_SOURCE, type RunState } from "@/lib/useRunEvents";

type Props = {
  chargeId: string;
  state: RunState;
  onAnswer: (questionId: string) => void;
  headingRef?: React.Ref<HTMLHeadingElement>;
};

/** A clicked number: which source it came from and the exact text, so a quote can light up that phrase. */
type Active = { id: string; text: string } | null;

const srcId = (chargeId: string, evidenceId: string) => `src-${chargeId}-${evidenceId.replace(/\W/g, "-")}`;

const WHY_TITLE: Record<string, string> = {
  split: "Why it's split",
  dispute: "Why it's disputed",
  accept: "Why it's fair",
  ask: "Why you're being asked",
  skip: "Why it's on hold",
};

// The decision-gate table in docs/design.md, in plain words. Copy only; the gate itself lives in api/engine/.
const GATE_ROW: Record<number, string> = {
  1: "A deal term this charge depends on failed the quote check, so Clawback can't verify it.",
  2: "The two deal readers disagree on a term, so you decide.",
  3: "The deal leaves this to discretion, and one of your saved rules covers it.",
  4: "The deal leaves this to discretion and no saved rule covers it, so you decide once.",
  5: "The charge matches the deal to within $1.",
  6: "Northmart took less than the deal allows. Clawback never asks for more.",
  7: "Northmart took too much, at least two sources back it, and the likely pushback has an answer.",
  8: "The amount is over $5,000, so you approve before anything is filed.",
  9: "Not clear enough to act on alone, so you decide.",
};

const PRIMARY_TITLE: Partial<Record<Evidence["kind"], string>> = {
  clause: "What the deal says",
  email: "The email that changes it",
  notice: "Northmart's notice",
  claim: "What Northmart claims",
};

export function EvidencePanel({ chargeId, state, onAnswer, headingRef }: Props) {
  const detail = useChargeDetail(chargeId, state.run?.run_id, DATA_SOURCE);
  const charge = state.charges[chargeId] ?? detail?.charge;
  const f = state.findings[chargeId];
  const d = state.decisions[chargeId];
  const rehearsal = state.rehearsals[chargeId];
  const rule = d?.rule_id ? state.rules[d.rule_id] : undefined;
  const question = openQuestionOf(state);
  const askingHere = d?.decision === "ask" && question?.charge_id === chargeId;
  const [active, setActive] = useState<Active>(null);

  const show = useCallback(
    (id: string, text: string) => {
      setActive({ id, text });
      const el = document.getElementById(srcId(chargeId, id));
      el?.scrollIntoView({ block: "nearest", behavior: matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth" });
    },
    [chargeId],
  );

  if (!charge) return null;

  // Only show what the run has reached: a rule, an answer or an approval appears once it happened.
  const visible = (detail?.evidence ?? []).filter((e) => {
    if (e.kind === "rule") return !!(e.rule_id && state.rules[e.rule_id]);
    if (e.kind === "person") return !!d?.rule_id || Object.values(state.questions).some((q) => q.charge_id === chargeId && q.answer);
    if (e.kind === "approval") return state.approval?.id === e.approval_id && state.approval?.status === "approved";
    return true;
  });
  const primary = visible.find((e) => e.quote && e.kind in PRIMARY_TITLE);
  const others = visible.filter((e) => e !== primary);
  const label = (id: string) => visible.find((e) => e.id === id)?.label ?? id;

  return (
    <article aria-labelledby={`ev-${chargeId}`} className="flex flex-col">
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <h2 id={`ev-${chargeId}`} ref={headingRef} tabIndex={-1} className="flex items-baseline gap-2 font-display text-[22px] font-semibold focus:outline-none">
            <span className="num text-[15px] font-normal text-muted">{chargeId}</span>
            {charge.description}
          </h2>
          <p className="mt-0.5 text-[16px] text-muted">
            {chargeLine(charge)}, <span className="num text-ink">{money(charge.amount)}</span> taken from this payment
          </p>
        </div>
        <Pill status={statusOf(d)} />
      </header>

      {!d || !f ? (
        <Checking />
      ) : (
        <>
          <p className="mt-5 max-w-[38rem] font-display text-[22px] leading-snug font-semibold tracking-[-0.005em] text-ink sm:text-[24px]">{d.reason}</p>
          <p className="mt-2 max-w-[40rem] text-[17px] text-muted">{f.finding}</p>

          <Allocation d={d} taken={charge.amount} />

          {askingHere && question && (
            <div className="mt-6 rounded-xl border border-ask/45 bg-ask-soft p-4">
              <p className="text-[17px]">{question.text}</p>
              {recordedAnswer(question.id) && (
                <button
                  type="button"
                  onClick={() => onAnswer(question.id)}
                  className="mt-3 rounded-lg bg-accent px-4 py-2.5 text-[16px] font-semibold text-white shadow-sm hover:brightness-110 dark:text-[#0f151c]"
                >
                  {sentence(recordedAnswer(question.id)!)}
                </button>
              )}
            </div>
          )}

          {primary?.quote && (
            <Section title={PRIMARY_TITLE[primary.kind]!} id="deal">
              <div id={srcId(chargeId, primary.id)} className="scroll-mt-24">
                <QuoteBlock quote={primary.quote} active={active?.id === primary.id ? active.text : null} large />
                <p className="mt-2 text-[14px] text-muted">
                  {primary.label}
                  {primary.sender && <> from {primary.sender}</>}
                </p>
              </div>
            </Section>
          )}

          {f.math.length > 0 && (
            <Section title="The math" id="math" note="Worked out in code, not by AI. Select a number to see where it comes from.">
              <MathLines parts={f.math} active={active} onPick={show} />
            </Section>
          )}

          <Section title={WHY_TITLE[d.decision]} id="why">
            <ul className="space-y-1.5">
              {rule && <Check>{rule.summary}</Check>}
              <Check ok={f.readers_agree}>{f.readers_agree ? "Both deal readers agree on the terms used" : "The two deal readers disagree on a term"}</Check>
              {f.evidence_ids.length > 1 && <Check>Backed by {f.evidence_ids.length} sources</Check>}
              {rehearsal?.answered && <Check>Answer ready for Northmart&apos;s likely pushback</Check>}
            </ul>
            <p className="mt-3 text-[15px] text-muted">
              {rule
                ? `Applied ${rule.label}, learned ${shortDate(rule.learned_at)}, approved by ${rule.approver.split(" ")[0]}.`
                : GATE_ROW[d.gate_row]}
            </p>
          </Section>

          <Section title="Ready for their pushback" id="comeback">
            {rehearsal ? (
              <div className="rounded-xl border border-line bg-sunk p-4">
                <p className="text-[16px] text-muted">Northmart may say</p>
                <p className="mt-0.5 text-[17px]">“{rehearsal.predicted_rebuttal}”</p>
                <p className="mt-3 text-[16px] text-muted">Clawback answers</p>
                <p className="mt-0.5 text-[17px]">{rehearsal.answer}</p>
                {rehearsal.answer_evidence_ids.length > 0 && (
                  <div className="mt-3 flex flex-wrap gap-1.5">
                    {rehearsal.answer_evidence_ids.map((id) => (
                      <button
                        key={id}
                        type="button"
                        onClick={() => show(id, "")}
                        className="rounded-full border border-line bg-panel px-2.5 py-0.5 text-[14px] text-ink hover:border-accent"
                      >
                        {label(id)}
                      </button>
                    ))}
                  </div>
                )}
              </div>
            ) : (
              <p className="text-[16px] text-muted">
                {d.decision === "dispute" || d.decision === "split" ? "No rehearsal recorded." : "Nothing to rehearse. Clawback doesn't argue with fair charges."}
              </p>
            )}
          </Section>

          {others.length > 0 && (
            <Section title="Sources" id="sources">
              <ul className="grid grid-cols-[minmax(0,1fr)] gap-2">
                {others.map((e) => (
                  <li
                    key={e.id}
                    id={srcId(chargeId, e.id)}
                    className={`scroll-mt-24 rounded-xl border p-3.5 transition-colors ${
                      active?.id === e.id ? "border-accent bg-panel ring-1 ring-accent" : "border-line-soft bg-sunk"
                    }`}
                  >
                    <SourceCard e={e} active={active?.id === e.id ? active.text : null} />
                  </li>
                ))}
              </ul>
            </Section>
          )}

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

function Check({ ok = true, children }: { ok?: boolean; children: ReactNode }) {
  return (
    <li className="flex gap-2.5 text-[16px]">
      {ok ? (
        <svg viewBox="0 0 16 16" width={16} height={16} className="mt-[4px] shrink-0" aria-hidden>
          <path d="M3.5 8.4 6.6 11.3 12.5 4.8" fill="none" stroke="var(--good)" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      ) : (
        <Glyph status="ask" className="mt-[4px]" />
      )}
      <span>{children}</span>
    </li>
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
function Allocation({ d, taken }: { d: Decision; taken: number }) {
  const parts = [
    { key: "fair", amount: d.accepted, label: "Fair, accepted", bar: "bg-accept/55", text: "text-muted" },
    { key: "over", amount: d.disputed, label: d.decision === "split" ? "Took too much, disputed" : "Disputed", bar: "hatch-dispute border border-dispute/60", text: "text-dispute" },
    { key: "wait", amount: d.waiting, label: d.decision === "ask" ? "Waiting on your answer" : "On hold", bar: "bg-ask/80", text: "text-ask" },
  ].filter((p) => p.amount > 0);
  if (parts.length === 0) return null;

  return (
    <figure className="mt-6" aria-label={`Of ${money(taken)} taken: ${parts.map((p) => `${money(p.amount)} ${p.label.toLowerCase()}`).join(", ")}`}>
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

/** The engine's math line, one clause per row (split on its " · " separators) so it reads top to bottom. */
function MathLines({ parts, active, onPick }: { parts: MathPart[]; active: Active; onPick: (id: string, text: string) => void }) {
  const lines: MathPart[][] = [[]];
  for (const p of parts) {
    if (p.evidence_id) {
      lines[lines.length - 1].push(p);
      continue;
    }
    p.text.split(" · ").forEach((chunk, i) => {
      if (i > 0) lines.push([]);
      if (chunk) lines[lines.length - 1].push({ text: chunk, evidence_id: null });
    });
  }
  return (
    <ol className="divide-y divide-line-soft overflow-hidden rounded-xl border border-line">
      {lines.map((line, li) => (
        <li key={li} className="num px-4 py-3 text-[17px] leading-relaxed">
          {line.map((p, i) =>
            p.evidence_id ? (
              <button
                key={i}
                type="button"
                onClick={() => onPick(p.evidence_id!, p.text)}
                title="Show where this number comes from"
                aria-pressed={active?.id === p.evidence_id && active.text === p.text}
                className={`num rounded px-0.5 underline decoration-dotted decoration-1 underline-offset-[5px] transition-colors hover:bg-highlight hover:text-highlight-ink ${
                  active?.id === p.evidence_id && active.text === p.text ? "bg-highlight text-highlight-ink" : "text-ink decoration-muted"
                }`}
              >
                {p.text}
              </button>
            ) : (
              <span key={i} className="font-sans text-[16px] whitespace-pre-wrap text-muted">
                {p.text.split(/(\$?\d[\d,]*(?:\.\d+)?)/).map((bit, j) =>
                  j % 2 ? (
                    <span key={j} className="num text-[17px]">
                      {bit}
                    </span>
                  ) : (
                    bit
                  ),
                )}
              </span>
            ),
          )}
        </li>
      ))}
    </ol>
  );
}

/** The sentence highlighted inside its paragraph; a clicked phrase found in it gets the strong highlight. */
function QuoteBlock({ quote, active, large }: { quote: Quote; active: string | null; large?: boolean }) {
  const at = active ? quote.text.indexOf(active) : -1;
  const body =
    at >= 0 ? (
      <>
        {quote.text.slice(0, at)}
        <span className="rounded-[2px] bg-highlight-strong">{active}</span>
        {quote.text.slice(at + active!.length)}
      </>
    ) : (
      quote.text
    );
  return (
    <blockquote className={`max-w-[40rem] whitespace-pre-line text-ink ${large ? "text-[19px] leading-[1.6]" : "text-[16px] leading-[1.55]"}`}>
      {quote.context_before && <span className="text-muted">{quote.context_before}</span>}
      <mark className="hl">
        {body}
      </mark>
      {quote.context_after && <span className="text-muted">{quote.context_after}</span>}
    </blockquote>
  );
}

const HIDDEN_COLUMNS = new Set(["id", "remittance_id", "promo_id", "code", "description"]);
const MONEY_COLUMNS = new Set(["amount", "rate"]);

function cell(key: string, v: string | number | null): string {
  if (v === null) return "—";
  if (typeof v === "number") return MONEY_COLUMNS.has(key) ? (key === "rate" ? rate(v) : money(v)) : units(v);
  if (/^\d{4}-\d{2}-\d{2}$/.test(v)) return shortDay(v);
  return v;
}

const header = (k: string) => sentence(k.replace(/_/g, " "));

function Rows({ rows }: { rows: Evidence["rows"] }) {
  const cols = Object.keys(rows[0]).filter((k) => !HIDDEN_COLUMNS.has(k) && rows.some((r) => r[k] !== null));
  if (rows.length === 1) {
    return (
      <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-0.5 text-[15px]">
        {cols.map((k) => {
          const v = cell(k, rows[0][k]);
          return (
            <div key={k} className="contents">
              <dt className="text-muted">{header(k)}</dt>
              <dd className={/^[$\d—]/.test(v) ? "num text-ink" : "text-ink"}>{v}</dd>
            </div>
          );
        })}
      </dl>
    );
  }
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-left text-[15px]">
        <thead>
          <tr>
            {cols.map((k) => (
              <th key={k} scope="col" className="pr-4 pb-1 font-normal whitespace-nowrap text-muted">
                {header(k)}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={i}>
              {cols.map((k) => {
                const v = cell(k, r[k]);
                return (
                  <td key={k} className={`pr-4 whitespace-nowrap ${/^[$\d—]/.test(v) ? "num" : ""}`}>
                    {v}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function SourceCard({ e, active }: { e: Evidence; active: string | null }) {
  return (
    <div>
      <p className="flex flex-wrap items-baseline gap-x-2 text-[14px] font-semibold text-muted">
        {e.label}
        {e.approved_sender === true && <span className="font-normal text-good">Approved sender</span>}
        {e.approved_sender === false && <span className="font-normal text-dispute">Can&apos;t change the deal</span>}
      </p>
      <p className="mt-1 text-[16px]">{e.summary}</p>
      {e.quote && (
        <div className="mt-2">
          <QuoteBlock quote={e.quote} active={active} />
        </div>
      )}
      {e.rows.length > 0 && (
        <div className="mt-2">
          <Rows rows={e.rows} />
        </div>
      )}
    </div>
  );
}

function NextSteps({ d, state }: { d: Decision; state: RunState }) {
  const who = CAST.controller;
  const filed = state.dispute?.lines.find((l) => l.charge_id === d.charge_id);
  const memo = state.ledger.find((p) => p.qbo_entity === "credit_memo");
  const a = state.approval;
  const inMemo = a?.lines.some((l) => l.charge_id === d.charge_id);
  const lines: ReactNode[] = [];

  if (d.disputed > 0) {
    lines.push(
      filed ? (
        <>
          <span className="num">{money(filed.amount)}</span> filed on Northmart&apos;s portal in dispute {state.dispute!.id}.
        </>
      ) : (
        <>Filing the dispute on Northmart&apos;s portal…</>
      ),
    );
  }
  if (d.accepted > 0) {
    const where =
      memo?.status === "posted" && inMemo
        ? "posted to QuickBooks in the credit memo."
        : a?.status === "refused" && inMemo
          ? `held by ${who}. Nothing posted.`
          : a?.status === "pending" && inMemo
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
