"use client";

import type { RemittanceLine } from "./types";

type Piece = { text: string; line?: RemittanceLine };

/** The remittance as it was read, split into plain text and each line's quote (its char_start..char_end). */
function pieces(text: string, lines: RemittanceLine[]): Piece[] {
  const spans = lines
    .filter((l) => l.char_start !== null && l.char_end !== null)
    .sort((a, b) => (a.char_start ?? 0) - (b.char_start ?? 0));
  const out: Piece[] = [];
  let at = 0;
  for (const l of spans) {
    const start = l.char_start ?? 0;
    const end = l.char_end ?? 0;
    if (start < at) continue; // the API never overlaps them; skip rather than garble the text
    if (start > at) out.push({ text: text.slice(at, start) });
    out.push({ text: text.slice(start, end), line: l });
    at = end;
  }
  if (at < text.length) out.push({ text: text.slice(at) });
  return out;
}

/** The source text with every line Clawback took from it highlighted; the picked line stands out. */
export default function RemittanceText({ text, lines, active, onPick }: {
  text: string;
  lines: RemittanceLine[];
  active: number | null;
  onPick: (n: number) => void;
}) {
  return (
    <pre
      className="m-0 max-h-[560px] overflow-auto rounded-[10px] border border-[var(--line)] bg-[var(--card)] p-3 font-mono text-[11.5px] leading-[1.7] text-[var(--ink)]"
      aria-label="The remittance as Clawback read it"
      tabIndex={0}
    >
      {pieces(text, lines).map((p, i) =>
        p.line ? (
          <mark
            key={i}
            id={`remit-quote-${p.line.n}`}
            onClick={() => onPick(p.line!.n)}
            className={`cursor-pointer rounded-[3px] text-inherit ${p.line.status === "verified" ? "bg-[var(--amber-bg)]" : "bg-[var(--amber-soft)] outline outline-1 outline-[var(--amber)]"} ${active === p.line.n ? "outline outline-2 outline-[var(--violet)]" : ""}`}
          >
            {p.text}
          </mark>
        ) : (
          <span key={i}>{p.text}</span>
        ),
      )}
    </pre>
  );
}
