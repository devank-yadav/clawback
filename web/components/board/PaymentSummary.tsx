"use client";

import { motion } from "framer-motion";
import { CAST } from "@/lib/cast";
import { money } from "@/lib/format";
import type { Approval, LedgerPost, Remittance, Totals } from "@/lib/types";
import type { FeedLine } from "@/lib/useRunEvents";
import { CountUp } from "./parts";

type Props = {
  remittance: Remittance | null;
  totals: Totals | null;
  approval: Approval | null;
  ledger: LedgerPost[];
  latest: FeedLine | undefined;
  playing: boolean;
};

function acceptedNote(approval: Approval | null, ledger: LedgerPost[]) {
  if (ledger.some((p) => p.qbo_entity === "credit_memo" && p.status === "posted")) return "Posted to QuickBooks";
  if (approval?.status === "refused") return `Held by ${CAST.controller}. Nothing posted`;
  if (approval?.status === "pending") return `Waiting on ${CAST.controller} to approve`;
  return `Goes to ${CAST.controller} once every charge is decided`;
}

export function PaymentSummary({ remittance: r, totals, approval, ledger, latest, playing }: Props) {
  // Bar widths are a share of what was taken: a display ratio, not a money calculation.
  const share = (n: number) => (totals && totals.taken > 0 ? `${(n / totals.taken) * 100}%` : "0%");

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
        {r ? (
          <div className="max-w-[40rem]">
            <p className="text-[15px] text-muted">Payment for invoice {r.invoice_id}</p>
            <h1 id="payment-heading" className="mt-1 font-display text-[28px] leading-[1.15] font-semibold tracking-[-0.01em] sm:text-[34px]">
              {r.counterparty} paid <span className="num font-medium tracking-[-0.04em]">{money(r.received)}</span> of{" "}
              <span className="num font-medium tracking-[-0.04em]">{money(r.expected)}</span>
            </h1>
            <p className="mt-2 text-[17px] text-muted">
              They kept <span className="num text-ink">{money(r.taken)}</span> across {r.charge_count} charges. Clawback checks each one
              against your signed deal.
            </p>
          </div>
        ) : (
          <div className="max-w-[40rem]" aria-busy="true">
            <h1 id="payment-heading" className="font-display text-[28px] font-semibold sm:text-[34px]">
              Waiting for the payment
            </h1>
            <div className="mt-3 h-5 w-80 max-w-full rounded bg-sunk" />
          </div>
        )}

        <p className="flex min-h-6 items-center gap-2 text-[15px] text-muted lg:max-w-[24rem] lg:justify-end lg:text-right" aria-live="polite">
          {playing && <span className="size-2 shrink-0 rounded-full bg-accent motion-safe:animate-pulse" aria-hidden />}
          {latest?.text}
        </p>
      </div>

      <div className="border-t border-line-soft px-5 pt-5 pb-6 sm:px-7">
        <div
          className="flex h-3 w-full overflow-hidden rounded-full bg-sunk"
          role="img"
          aria-label={
            totals
              ? `${money(totals.disputed)} disputing, ${money(totals.accepted)} accepted, ${money(totals.waiting)} waiting on you, ${money(totals.undecided)} still being checked, of ${money(totals.taken)} taken`
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
          <Meter tone="dispute" label="Disputing" value={totals?.disputed ?? 0} note={totals?.disputed ? "Filed with Northmart as one dispute" : "Nothing yet"} />
          <Meter tone="accept" label="Accepted" value={totals?.accepted ?? 0} note={totals?.accepted ? acceptedNote(approval, ledger) : "Nothing yet"} />
          <Meter
            tone="ask"
            label="Waiting on you"
            value={totals?.waiting ?? 0}
            note={totals?.waiting ? `${totals.questions} ${totals.questions === 1 ? "question" : "questions"} for you` : "Nothing waiting on you"}
            dim={!totals?.waiting}
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
