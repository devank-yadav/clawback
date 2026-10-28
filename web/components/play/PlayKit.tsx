"use client";

// The design system's play kit (Clawback design system, components/src/play.js), as typed React: a run shown one
// deduction at a time, as a card that gets stamped. Styles are in app/game.css (cb-stamp, cb-deduction, cb-score,
// cb-queue, cb-decide). Every amount is passed in from the run; nothing here computes money or scores the user.

import { useEffect, useRef, useState, type ReactNode } from "react";

export type Verdict = "dispute" | "split" | "fair" | "ask" | "skip";

const VERDICT: Record<Verdict, { word: string; tone: "dispute" | "fair" | "wait" | "neutral" }> = {
  dispute: { word: "Claw back", tone: "dispute" },
  split: { word: "Part back", tone: "dispute" },
  fair: { word: "Fair", tone: "fair" },
  ask: { word: "Your call", tone: "wait" },
  skip: { word: "Can’t verify", tone: "neutral" },
};

function money(n: number) {
  const v = Math.abs(n);
  const cents = Math.round(v * 100) % 100 !== 0;
  return `${n < 0 ? "−$" : "$"}${v.toLocaleString("en-US", { minimumFractionDigits: cents ? 2 : 0, maximumFractionDigits: 2 })}`;
}

/** An amount that counts from its last value to the new one over duration-count; jumps under reduced motion. */
function useCount(target: number) {
  const shown = useRef(target);
  const [value, setValue] = useState(target);
  useEffect(() => {
    const from = shown.current;
    const reduce = typeof window !== "undefined" && window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
    if (reduce || from === target) { shown.current = target; setValue(target); return; }
    let t0: number | null = null;
    let raf = 0;
    const step = (t: number) => {
      if (t0 === null) t0 = t;
      const p = Math.min(1, (t - t0) / 600);
      shown.current = from + (target - from) * (1 - Math.pow(1 - p, 3));
      setValue(shown.current);
      if (p < 1) raf = requestAnimationFrame(step);
    };
    raf = requestAnimationFrame(step);
    return () => cancelAnimationFrame(raf);
  }, [target]);
  return value;
}

export function Spinner({ size = 18 }: { size?: number }) {
  return (
    <span className="cb-spinner" aria-hidden="true">
      <svg width={size} height={size} viewBox="0 0 24 24" fill="none"><circle cx="12" cy="12" r="9" stroke="currentColor" strokeWidth="3" strokeDasharray="40 17" strokeLinecap="round" /></svg>
    </span>
  );
}

/** The rubber stamp a decided charge gets: one word and the amount it applies to. */
export function VerdictStamp({ verdict, amount, still }: { verdict: Verdict; amount?: number | null; still?: boolean }) {
  const v = VERDICT[verdict];
  return (
    <span className={`cb-stamp is-${v.tone} ${still ? "is-still" : ""}`}>
      <b>{v.word}</b>
      {amount != null && <span className="cb-stamp-amt">{money(amount)}{verdict === "split" ? " back" : ""}</span>}
    </span>
  );
}

type DeductionCardProps = {
  title: ReactNode;
  amount: number;
  code?: string;
  meta?: ReactNode;
  state?: "waiting" | "checking";
  verdict?: Verdict | null;
  /** For a split: the part being clawed back. */
  back?: number | null;
  reason?: ReactNode;
  agent?: ReactNode;
  onOpen?: () => void;
  openLabel?: string;
};

/** One deduction as a card: waiting (up next), checking (an agent at work), or decided (stamped, with the reason). */
export function DeductionCard({ title, amount, code, meta, state = "waiting", verdict, back, reason, agent, onOpen, openLabel }: DeductionCardProps) {
  const phase = verdict ? "decided" : state;
  const tone = verdict ? VERDICT[verdict].tone : "";
  const stampAmount = verdict === "split" ? back ?? null : verdict === "ask" ? null : amount;
  return (
    <article className={`cb-deduction is-${phase} ${tone ? `is-${tone}` : ""}`} aria-label={typeof title === "string" ? title : undefined}>
      <div className="cb-deduction-top">
        {code && <span className="cx-tag">{code}</span>}
        {meta && <span className="cb-deduction-meta">{meta}</span>}
      </div>
      <h3 className="cb-deduction-title">{title}</h3>
      <p className="cb-deduction-amt"><small>They kept</small><strong>{money(amount)}</strong></p>
      {phase === "checking" && <i className="cb-scan" aria-hidden="true" />}
      {phase === "checking" && <div className="cb-deduction-work" role="status"><Spinner /><span>{agent ?? "The agents are checking it"}</span></div>}
      {phase === "waiting" && <p className="cb-deduction-wait">Up next</p>}
      {phase === "decided" && verdict === "split" && back != null && (
        <p className="cb-deduction-split"><span className="is-dispute">Back <b>{money(back)}</b></span><span className="is-fair">Fair <b>{money(amount - back)}</b></span></p>
      )}
      {phase === "decided" && reason && <p className="cb-deduction-why">{reason}</p>}
      {verdict && <div className="cb-deduction-stamp"><VerdictStamp verdict={verdict} amount={stampAmount} /></div>}
      {phase === "decided" && onOpen && <button type="button" className="cx-btn is-ghost is-small cb-deduction-open" onClick={onOpen}>{openLabel ?? "See the proof"}</button>}
    </article>
  );
}

/** Where the money stands: the amount being clawed back, the fair total, questions, one pip per real charge. */
export function Scoreboard({ back, fair, questions = 0, pips = [], current, label, line }: {
  back: number; fair: number; questions?: number; pips?: (Verdict | null)[]; current?: number; label?: string; line?: ReactNode;
}) {
  const b = useCount(back);
  const f = useCount(fair);
  const done = pips.filter((v) => v && v !== "ask").length;
  return (
    <section className="cb-score" aria-label="Where the money stands">
      <div className="cb-score-main">
        <span className="cb-score-label">{label ?? "Getting back"}</span>
        <strong className="cb-score-big">{money(Math.round(b))}</strong>
        {line && <span className="cb-score-line">{line}</span>}
      </div>
      <div className="cb-score-cells">
        <div className="cb-score-cell is-fair"><span>Fair charges</span><b>{money(Math.round(f))}</b></div>
        <div className="cb-score-cell is-wait"><span>Questions for you</span><b>{questions ? `${questions} question${questions === 1 ? "" : "s"}` : "None"}</b></div>
      </div>
      {pips.length > 0 && (
        <div className="cb-score-pips">
          <ol aria-label={`${done} of ${pips.length} charges decided`}>
            {pips.map((v, i) => (
              <li key={i} className={`cb-pip ${v ? `is-${VERDICT[v].tone}` : ""} ${i === current ? "is-current" : ""}`} title={v ? VERDICT[v].word : i === current ? "Checking" : "Up next"} />
            ))}
          </ol>
          <span className="cb-score-count">{done} of {pips.length} decided</span>
        </div>
      )}
    </section>
  );
}

/** Every charge of the payment as a small card in a row; decided ones carry their pile's color and word. */
export function CardQueue({ cards, current, onPick, label }: {
  cards: { id: string; title: ReactNode; amount: number; verdict?: Verdict | null }[]; current?: string; onPick?: (id: string) => void; label?: string;
}) {
  return (
    <ol className="cb-queue" aria-label={label ?? "Charges in this payment"}>
      {cards.map((c) => {
        const v = c.verdict ? VERDICT[c.verdict] : null;
        const cur = c.id === current;
        return (
          <li key={c.id}>
            <button type="button" className={`cb-qcard ${v ? `is-${v.tone}` : ""} ${cur ? "is-current" : ""}`} aria-current={cur ? "true" : undefined}
              onClick={onPick && v ? () => onPick(c.id) : undefined} disabled={!onPick || !v}>
              <span className="cb-qcard-title">{c.title}</span>
              <span className="cb-qcard-amt">{money(c.amount)}</span>
              <span className="cb-qcard-word">{v ? v.word : cur ? "Checking" : "Up next"}</span>
            </button>
          </li>
        );
      })}
    </ol>
  );
}

/** The one question: plain words, big choices with what each does to the money, remember-it, one button. */
export function DecisionCard({ question, why, quote, quoteSource, level, amount, choices, remember: rememberDefault = true, rememberLabel, goLabel, busy, onDecide }: {
  question: ReactNode; why?: ReactNode; quote?: ReactNode; quoteSource?: ReactNode; level?: "High" | "Medium" | "Low" | null; amount?: number;
  choices: { value: string; label: ReactNode; consequence?: ReactNode }[]; remember?: boolean; rememberLabel?: string | null; goLabel?: string; busy?: boolean;
  onDecide: (value: string, remember: boolean) => void;
}) {
  const [pick, setPick] = useState<string | null>(null);
  const [remember, setRemember] = useState(rememberDefault);
  return (
    <section className="cb-decide" aria-label="Your call">
      <div className="cb-decide-top">
        <span className="cx-pill is-amber">Your call</span>
        {level && <span className={`cb-level is-${level.toLowerCase()}`}>{level}</span>}
        {amount != null && <span className="cb-decide-amt">{money(amount)} at stake</span>}
      </div>
      <h2 className="cb-decide-q">{question}</h2>
      {why && <p className="cb-decide-why">{why}</p>}
      {quote && <figure className="cb-quote"><blockquote>{quote}</blockquote>{quoteSource && <figcaption>{quoteSource}</figcaption>}</figure>}
      <div className="cb-choices" role="radiogroup" aria-label="Your choices">
        {choices.map((c) => (
          <button key={c.value} type="button" role="radio" aria-checked={c.value === pick} className={`cb-choice ${c.value === pick ? "is-on" : ""}`} onClick={() => setPick(c.value)}>
            <b>{c.label}</b>{c.consequence && <span>{c.consequence}</span>}
          </button>
        ))}
      </div>
      {rememberLabel !== null && (
        <label className="cb-check">
          <input type="checkbox" checked={remember} onChange={(e) => setRemember(e.target.checked)} />
          <span className="cb-check-box" aria-hidden="true"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3.4" strokeLinecap="round" strokeLinejoin="round"><path d="M5 12.5l4.5 4.5L19 7.5" /></svg></span>
          <span className="cb-check-text"><span>{rememberLabel ?? "Remember this for next time"}</span></span>
        </label>
      )}
      <div className="cb-decide-go">
        <button type="button" className="cx-btn is-blue" disabled={!pick || busy} onClick={() => pick && onDecide(pick, remember)}>{busy ? "Saving…" : goLabel ?? "Decide"}</button>
      </div>
    </section>
  );
}
