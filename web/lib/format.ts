// Formatting only. Amounts arrive from the API; nothing here does arithmetic on them.

const whole = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 0 });
const cents = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", minimumFractionDigits: 2 });
const count = new Intl.NumberFormat("en-US");
const day = new Intl.DateTimeFormat("en-US", { month: "short", day: "numeric", timeZone: "America/Los_Angeles" });
const isoDay = new Intl.DateTimeFormat("en-US", { month: "short", day: "numeric", timeZone: "UTC" });

/** $1,200 for whole dollars, $1,200.50 otherwise. */
export const money = (n: number) => (Number.isInteger(n) ? whole : cents).format(n);

/** Per-bar rates always show cents: $1.00, $1.50. */
export const rate = (n: number) => cents.format(n);

export const units = (n: number) => count.format(n);

/** "Oct 24" from a datetime with offset, in the demo's time zone. */
export const shortDate = (iso: string) => day.format(new Date(iso));

/** "Mar 11" from a YYYY-MM-DD date. */
export const shortDay = (ymd: string) => isoDay.format(new Date(`${ymd}T00:00:00Z`));

/** $1,200.00: the workspace screens always show cents. */
export const dollars = (n: number) => cents.format(n);

/** Percent of `whole`, for bar widths only. Layout, not accounting: amounts and decisions come from the API. */
export const share = (part: number, whole: number) => (whole > 0 ? Math.min(100, Math.max(0, (part / whole) * 100)) : 0);

const compactFmt = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", notation: "compact", maximumFractionDigits: 1 });
const monthShort = new Intl.DateTimeFormat("en-US", { month: "short", timeZone: "UTC" });
const monthLong = new Intl.DateTimeFormat("en-US", { month: "long", year: "numeric", timeZone: "UTC" });

/** $48K, $1.2M: chart ticks and tight tiles. */
export const compactMoney = (n: number) => compactFmt.format(n);

/** 42% from 0.42 (or from 42, if the API sends a percent). */
export const percent = (n: number) => `${Math.round((n > 1 ? n : n * 100) * 10) / 10}%`;

const asMonth = (m: string) => (/^\d{4}-\d{2}/.test(m) ? new Date(`${m.slice(0, 7)}-01T00:00:00Z`) : null);

/** "Mar" from "2026-03" or "2026-03-01"; anything else is shown as sent. */
export const monthShortLabel = (m: string) => {
  const d = asMonth(m);
  return d ? monthShort.format(d) : m;
};

/** "March 2026" from "2026-03"; anything else is shown as sent. */
export const monthLabel = (m: string) => {
  const d = asMonth(m);
  return d ? monthLong.format(d) : m;
};

/** "Mar 11" from a date or a datetime. */
export const anyDay = (s: string) => (/^\d{4}-\d{2}-\d{2}$/.test(s) ? shortDay(s) : Number.isNaN(Date.parse(s)) ? s : shortDate(s));

/** "10:30:16 AM" from a datetime, for the trace. */
export const clock = (iso: string) => {
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit", second: "2-digit" });
};

/** "71 s" under two minutes, "3 min" after. */
export const duration = (seconds: number) => (seconds < 120 ? `${Math.round(seconds)} s` : `${Math.round(seconds / 60)} min`);

/** "$0.38" for the AI cost of a run; under a cent shows as "under $0.01". */
export const aiCost = (usd: number) => (usd > 0 && usd < 0.01 ? "under $0.01" : cents.format(usd));

/** "45 min" or "2.5 h" for the hand-work estimate. */
export const minutesLabel = (m: number) => (m < 90 ? `${Math.round(m)} min` : `${Math.round((m / 60) * 10) / 10} h`);

/** "12 days left", "1 day left", "Last day", "Window closed". */
export const daysLeftLabel = (d: number) => (d > 1 ? `${d} days left` : d === 1 ? "1 day left" : d === 0 ? "Last day" : "Window closed");

/** Under this many days a file-by date shows as urgent. */
export const URGENT_DAYS = 14;
