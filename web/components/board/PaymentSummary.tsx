"use client";

import { motion } from "framer-motion";
import { money } from "@/lib/format";
import { REMITTANCE } from "@/lib/prototype/run";
import type { ApprovalData, LedgerPostData, TotalsData } from "@/lib/types";
import type { FeedLine } from "@/lib/useRunEvents";
import { CountUp } from "./parts";

type Props = {
  totals: TotalsData | null;
  approval: ApprovalData | null;
  ledger: LedgerPostData[];
  latest: FeedLine | undefined;
  running: boolean;
};

function acceptedNote(approval: ApprovalData | null, ledger: LedgerPostData[]) {
  if (ledger.some((p) => p.entity === "Credit memo" && p.status === "posted")) return "Posted to QuickBooks";
  if (approval?.status === "refused") return `Held by ${REMITTANCE.controller}. Nothing posted`;
  if (approval?.status === "pending") return `Waiting on ${REMITTANCE.controller} to approve`;
  return `Goes to ${REMITTANCE.controller} after your answer`;
}

export function PaymentSummary({ totals, approval, ledger, latest, running }: Props) {
  const r = REMITTANCE;
  // Bar widths are a share of what was taken: a display ratio, not a money calculation.
  const share = (n: number) => `${(n / r.taken) * 100}%`;

  const segments = totals
    ? [
        { key: "dispute", value: totals.disputed, cls: "bg-dispute" },
        { key: "accept", value: totals.accepted, cls: "bg-accept/55" },
        { key: "ask", value: totals.waiting, cls: "bg-ask" },
      ]
    : [];

  return (
    <section aria-labelledby="payment-heading" className="rounded-2xl border border-line bg-panel">
      <div className="flex flex-col gap-6 p-5 sm:p-7 lg:flex-row lg:items-end lg:justify-between">
        <div className="max-w-[40rem]">
          <p className="text-[15px] text-muted">
            {r.month} payment for invoice {r.invoice}
          </p>
          <h1 id="payment-heading" className="mt-1 font-display text-[28px] leading-[1.15] font-semibold tracking-[-0.01em] sm:text-[34px]">
            {r.counterparty} paid <span className="num font-medium tracking-[-0.04em]">{money(r.received)}</span> of{" "}
            <span className="num font-medium tracking-[-0.04em]">{money(r.expected)}</span>
          </h1>
          <p className="mt-2 text-[17px] text-muted">
            They kept <span className="num text-ink">{money(r.taken)}</span> across {r.charges} charges. Clawback checked each
            one against your signed deal.
          </p>
        </div>

        <p className="flex min-h-6 items-center gap-2 text-[15px] text-muted lg:max-w-[22rem] lg:justify-end lg:text-right" aria-live="polite">
          {running && <span className="size-2 shrink-0 rounded-full bg-accent motion-safe:animate-pulse" aria-hidden />}
          {latest?.text}
        </p>
      </div>

      <div className="border-t border-line-soft px-5 pt-5 pb-6 sm:px-7">
        <div
          className="flex h-3 w-full overflow-hidden rounded-full bg-sunk"
          role="img"
          aria-label={
            totals
              ? `${money(totals.disputed)} disputing, ${money(totals.accepted)} accepted, ${money(totals.waiting)} waiting on you, of ${money(r.taken)} taken`
              : "Checking charges"
          }
        >
          {segments.map((s) => (
            <motion.div
              key={s.key}
              className={`${s.cls} h-full first:rounded-l-full`}
              initial={false}
              animate={{ width: share(s.value) }}
              transition={{ duration: 0.6, ease: [0.22, 1, 0.36, 1] }}
            />
          ))}
        </div>

        <dl className="mt-4 grid grid-cols-3 items-end gap-x-3 gap-y-4 sm:items-start sm:gap-x-8">
          <Meter tone="dispute" label="Disputing" value={totals?.disputed ?? 0} note={totals?.disputed ? "Filed as dispute D-0417" : "—"} />
          <Meter tone="accept" label="Accepted" value={totals?.accepted ?? 0} note={totals ? acceptedNote(approval, ledger) : "—"} />
          <Meter
            tone="ask"
            label="Waiting on you"
            value={totals?.waiting ?? 0}
            note={totals?.waiting ? "1 question about the display fee" : totals ? "Nothing waiting on you" : "—"}
            dim={!!totals && totals.waiting === 0}
          />
        </dl>
      </div>
    </section>
  );
}

const SWATCH = { dispute: "bg-dispute", accept: "bg-accept/55", ask: "bg-ask" } as const;

function Meter({ tone, label, value, note, dim }: { tone: keyof typeof SWATCH; label: string; value: number; note: string; dim?: boolean }) {
  return (
    <div className={dim ? "opacity-60" : ""}>
      <dt className="flex items-center gap-2 text-[14px] text-muted sm:text-[15px]">
        <span className={`size-2.5 shrink-0 rounded-[3px] ${SWATCH[tone]}`} aria-hidden />
        {label}
      </dt>
      <dd className="mt-0.5">
        <CountUp value={value} className="text-[19px] font-medium text-ink sm:text-[24px]" />
        <span className="hidden text-[14px] text-muted sm:block">{note}</span>
      </dd>
    </div>
  );
}
