// Formatting only. Amounts arrive from the API or the fixture; nothing here does arithmetic on them.

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
