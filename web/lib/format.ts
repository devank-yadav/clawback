// Formatting only. Amounts arrive from the API (or prototype data); nothing here does arithmetic on them.

const usd = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 0 });

export const money = (n: number) => usd.format(n);
