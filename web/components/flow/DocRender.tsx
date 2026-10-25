// A small, safe renderer for the contract library's documents: markdown-ish text (headings, bold, lists, tables,
// signature blocks) and text converted from SEC filings (dashed rules, box drawing, column-aligned rows) become plain
// React elements. No HTML from a document is ever injected. Every piece of text keeps its character offset in the
// original, so the deal readers' highlights (char_start / char_end) still mark exactly the clauses they read.

import type { ReactNode } from "react";
import type { LibraryTerm } from "@/lib/types";

type Range = { start: number; end: number };
export type OutlineItem = { id: string; label: string; level: number };

const RULE = /^[\s\-=_*~+|─━│┃┌┐└┘├┤┬┴┼═║╔╗╚╝╠╣╦╩╬]+$/;
const BOX = /[─━│┃┌┐└┘├┤┬┴┼═║╔╗╚╝╠╣╦╩╬]/;
const HEADING = /^(#{1,6})\s+/;
const BULLET = /^\s*([-*•])\s+/;
const TABLE_SEP = /^\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?\s*$/;
const COLUMNS = /\S\s{3,}\S/;

type Line = { text: string; start: number };

function linesOf(text: string): Line[] {
  const out: Line[] = [];
  let start = 0;
  for (const part of text.split("\n")) {
    out.push({ text: part, start });
    start += part.length + 1;
  }
  return out;
}

/** The inline pieces of [start, end): bold toggled by "**", "[***]" kept as a redaction, every piece at its offset. */
function inline(text: string, start: number, end: number, terms: LibraryTerm[], active: number | null, onPick: (i: number) => void): ReactNode[] {
  const pieces: { s: number; e: number; bold: boolean; redacted?: boolean }[] = [];
  let bold = false;
  let i = start;
  let from = start;
  while (i < end) {
    if (text.startsWith("[***]", i)) {
      if (i > from) pieces.push({ s: from, e: i, bold });
      pieces.push({ s: i, e: i + 5, bold, redacted: true });
      i += 5;
      from = i;
      continue;
    }
    if (text.startsWith("**", i)) {
      if (i > from) pieces.push({ s: from, e: i, bold });
      bold = !bold;
      i += 2;
      from = i;
      continue;
    }
    i++;
  }
  if (end > from) pieces.push({ s: from, e: end, bold });

  const out: ReactNode[] = [];
  for (const p of pieces) {
    if (p.redacted) {
      out.push(<span key={`r${p.s}`} className="dr-redacted" title="Redacted in the filing">redacted</span>);
      continue;
    }
    // Split the piece where a highlighted term starts or ends.
    const cuts = new Set([p.s, p.e]);
    terms.forEach((t) => {
      if (t.char_start > p.s && t.char_start < p.e) cuts.add(t.char_start);
      if (t.char_end > p.s && t.char_end < p.e) cuts.add(t.char_end);
    });
    const points = [...cuts].sort((a, b) => a - b);
    for (let k = 0; k < points.length - 1; k++) {
      const a = points[k], b = points[k + 1];
      const slice = text.slice(a, b);
      const ti = terms.findIndex((t) => t.char_start <= a && t.char_end >= b);
      const node = p.bold ? <strong key={`b${a}`}>{slice}</strong> : slice;
      if (ti >= 0) {
        const t = terms[ti];
        out.push(
          <mark key={`m${a}`} data-term={ti} className={`ct-mark is-${t.status} ${t.discretion ? "is-discretion" : ""} ${active === ti ? "is-active" : ""}`} onClick={() => onPick(ti)} title={t.label}>{node}</mark>,
        );
      } else out.push(typeof node === "string" ? <span key={`t${a}`}>{node}</span> : node);
    }
  }
  return out;
}

/** The cells of a table row, each with its range in the original text. */
function cells(line: Line, splitter: RegExp | "pipes"): Range[] {
  const out: Range[] = [];
  if (splitter === "pipes") {
    let s = line.start;
    const body = line.text;
    let i = 0;
    if (body.trimStart().startsWith("|")) { i = body.indexOf("|") + 1; s = line.start + i; }
    for (; i <= body.length; i++) {
      if (i === body.length || body[i] === "|") {
        const e = line.start + i;
        if (i !== body.length || e > s) out.push({ start: s, end: e });
        s = e + 1;
      }
    }
    return out.filter((r, k, all) => !(k === all.length - 1 && r.end <= r.start));
  }
  const re = new RegExp(splitter.source, "g");
  let s = 0;
  let m: RegExpExecArray | null;
  while ((m = re.exec(line.text))) {
    out.push({ start: line.start + s, end: line.start + m.index });
    s = m.index + m[0].length;
  }
  out.push({ start: line.start + s, end: line.start + line.text.length });
  return out;
}

const trim = (text: string, r: Range): Range => {
  let { start, end } = r;
  while (start < end && /\s/.test(text[start])) start++;
  while (end > start && /\s/.test(text[end - 1])) end--;
  return { start, end };
};

export function renderDocument(text: string, terms: LibraryTerm[], active: number | null, onPick: (i: number) => void): { nodes: ReactNode[]; outline: OutlineItem[] } {
  const lines = linesOf(text);
  const nodes: ReactNode[] = [];
  const outline: OutlineItem[] = [];
  const sorted = terms;
  const span = (r: Range) => inline(text, r.start, r.end, sorted, active, onPick);
  let i = 0;
  let lastWasRule = false;

  while (i < lines.length) {
    const line = lines[i];
    const t = line.text;
    if (!t.trim()) { i++; continue; }

    // A heading.
    const h = HEADING.exec(t);
    if (h) {
      const level = Math.min(h[1].length, 4);
      const r = trim(text, { start: line.start + h[0].length, end: line.start + t.length });
      const id = `sec-${line.start}`;
      const label = text.slice(r.start, r.end).replace(/\*\*/g, "");
      if (level <= 3) outline.push({ id, label, level });
      const Tag = (level === 1 ? "h2" : level === 2 ? "h3" : "h4") as "h2" | "h3" | "h4";
      nodes.push(<Tag key={id} id={id} className="dr-h">{span(r)}</Tag>);
      lastWasRule = false;
      i++;
      continue;
    }

    // A rule: dashes, equals or box drawing on their own. Consecutive rules collapse into one.
    if (RULE.test(t) && t.trim().length >= 3) {
      if (!lastWasRule) nodes.push(<hr key={`hr${line.start}`} className="dr-hr" />);
      lastWasRule = true;
      i++;
      continue;
    }
    lastWasRule = false;

    // A markdown table: consecutive lines starting with "|".
    if (t.trimStart().startsWith("|")) {
      const rows: Line[] = [];
      while (i < lines.length && lines[i].text.trimStart().startsWith("|")) { rows.push(lines[i]); i++; }
      const body = rows.filter((r) => !TABLE_SEP.test(r.text));
      const hasHead = rows.length > 1 && TABLE_SEP.test(rows[1]?.text ?? "");
      nodes.push(
        <table key={`t${line.start}`} className="dr-table">
          <tbody>
            {body.map((r, k) => (
              <tr key={r.start}>
                {cells(r, "pipes").map((c) => trim(text, c)).map((c, j) => {
                  const Cell = hasHead && k === 0 ? "th" : "td";
                  return <Cell key={j}>{span(c)}</Cell>;
                })}
              </tr>
            ))}
          </tbody>
        </table>,
      );
      continue;
    }

    // Column-aligned text from a converted filing: two or more lines with wide gaps become a table.
    if (COLUMNS.test(t) && !BOX.test(t) && i + 1 < lines.length && COLUMNS.test(lines[i + 1].text)) {
      const rows: Line[] = [];
      while (i < lines.length && lines[i].text.trim() && COLUMNS.test(lines[i].text) && !RULE.test(lines[i].text)) { rows.push(lines[i]); i++; }
      nodes.push(
        <table key={`c${line.start}`} className="dr-table is-columns">
          <tbody>
            {rows.map((r) => <tr key={r.start}>{cells(r, /\s{3,}/).map((c) => trim(text, c)).map((c, j) => <td key={j}>{span(c)}</td>)}</tr>)}
          </tbody>
        </table>,
      );
      continue;
    }

    // A list.
    if (BULLET.test(t)) {
      const items: Range[] = [];
      while (i < lines.length && BULLET.test(lines[i].text)) {
        const m = BULLET.exec(lines[i].text)!;
        items.push(trim(text, { start: lines[i].start + m[0].length, end: lines[i].start + lines[i].text.length }));
        i++;
      }
      nodes.push(<ul key={`u${line.start}`} className="dr-list">{items.map((r) => <li key={r.start}>{span(r)}</li>)}</ul>);
      continue;
    }

    // A paragraph: consecutive plain lines; box-drawing characters inside are dropped.
    const para: Range[] = [];
    while (i < lines.length) {
      const l = lines[i];
      if (!l.text.trim() || HEADING.test(l.text) || (RULE.test(l.text) && l.text.trim().length >= 3) || l.text.trimStart().startsWith("|") || BULLET.test(l.text)) break;
      para.push(trim(text, { start: l.start, end: l.start + l.text.length }));
      i++;
      if (para.length && /^\d+(\.\d+)*[.)]?\s/.test(lines[i]?.text ?? "")) break; // a numbered clause starts its own paragraph
    }
    const parts: ReactNode[] = [];
    para.forEach((r, k) => {
      if (k) parts.push(" ");
      parts.push(...span(r).map((n) => (typeof n === "string" ? n.replace(new RegExp(BOX.source, "g"), " ") : n)));
    });
    const lead = text.slice(para[0].start, para[0].end);
    const numbered = /^\d+(\.\d+)*[.)]?\s/.test(lead);
    nodes.push(<p key={`p${line.start}`} className={`dr-p ${numbered ? "is-clause" : ""}`}>{parts}</p>);
  }
  return { nodes, outline };
}
