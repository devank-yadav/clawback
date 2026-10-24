// Reads the run's trace totals and a call's token usage. The API's exact field names aren't settled, so each value is
// looked up under the few names it is likely to have; anything missing is simply not shown. Display only.

import type { TraceSummary } from "./types";

const num = (v: unknown): number | null => (typeof v === "number" && Number.isFinite(v) ? v : null);

function pick(o: Record<string, unknown> | null | undefined, ...keys: string[]): number | null {
  if (!o) return null;
  for (const k of keys) {
    const v = num(o[k]);
    if (v !== null) return v;
  }
  return null;
}

export type Usage = { input: number | null; output: number | null; total: number | null };

/** {input_tokens, output_tokens} (Anthropic), {prompt_tokens, completion_tokens}, or {input, output, total}. */
export function readUsage(u: Record<string, unknown> | null | undefined): Usage | null {
  if (!u) return null;
  const input = pick(u, "input_tokens", "prompt_tokens", "input", "prompt_token_count");
  const output = pick(u, "output_tokens", "completion_tokens", "output", "candidates_token_count");
  const total = pick(u, "total_tokens", "total", "total_token_count");
  return input === null && output === null && total === null ? null : { input, output, total };
}

export type RunTotals = { calls: number | null; tokens: Usage | null; aiMs: number | null; wallMs: number | null; costUsd: number | null };

export function readSummary(s: TraceSummary | null): RunTotals | null {
  if (!s) return null;
  const tokens = typeof s.tokens === "object" && s.tokens !== null ? readUsage(s.tokens as Record<string, unknown>) : num(s.tokens) !== null ? { input: null, output: null, total: num(s.tokens) } : readUsage(s);
  const seconds = (msKeys: string[], sKeys: string[]) => {
    const ms = pick(s, ...msKeys);
    if (ms !== null) return ms;
    const sec = pick(s, ...sKeys);
    return sec === null ? null : sec * 1000;
  };
  return {
    calls: pick(s, "calls", "ai_calls", "count"),
    tokens,
    aiMs: seconds(["ai_ms", "ai_time_ms", "latency_ms"], ["ai_s", "ai_seconds", "ai_time_s"]),
    wallMs: seconds(["wall_ms", "wall_time_ms", "elapsed_ms"], ["wall_s", "wall_seconds", "wall_time_s"]),
    costUsd: pick(s, "cost_usd", "cost", "usd"),
  };
}

const count = new Intl.NumberFormat("en-US");
export const tokens = (n: number) => count.format(Math.round(n));

/** "1.8 s", "41 s", "2 min 5 s". */
export function duration(ms: number | null): string | null {
  if (ms === null) return null;
  if (ms < 1000) return `${Math.round(ms)} ms`;
  const s = ms / 1000;
  if (s < 10) return `${(Math.round(s * 10) / 10).toFixed(1)} s`;
  if (s < 90) return `${Math.round(s)} s`;
  return `${Math.floor(s / 60)} min ${Math.round(s % 60)} s`;
}

/** AI spend is shown to the cent, or to the tenth of a cent below a dollar. */
export const cost = (usd: number) => `$${usd < 1 ? usd.toFixed(3) : usd.toFixed(2)}`;
