"use client";

import { AnimatePresence, MotionConfig, motion } from "framer-motion";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useCallback, useEffect, useRef, useSyncExternalStore } from "react";
import { EvidencePanel } from "@/components/evidence/EvidencePanel";
import { CAST } from "@/lib/cast";
import { chargeDetail } from "@/lib/fixture";
import { useRunEvents } from "@/lib/useRunEvents";
import { ActivityFeed } from "./ActivityFeed";
import { ChargeList } from "./ChargeList";
import { PaymentSummary } from "./PaymentSummary";
import { PrototypeBadge } from "./parts";

const DESKTOP = "(min-width: 1024px)";

function useIsDesktop() {
  return useSyncExternalStore(
    (cb) => {
      const m = matchMedia(DESKTOP);
      m.addEventListener("change", cb);
      return () => m.removeEventListener("change", cb);
    },
    () => matchMedia(DESKTOP).matches,
    () => true,
  );
}

export default function ReviewBoard({ runId }: { runId: string }) {
  const { state, answerQuestion, controllerDecides, awaitingPayment, error, source } = useRunEvents(runId);
  const isDesktop = useIsDesktop();
  const router = useRouter();
  const pathname = usePathname();
  const params = useSearchParams();
  const pushed = useRef(false);
  const lastRow = useRef<HTMLElement | null>(null);
  const sheetHeading = useRef<HTMLHeadingElement>(null);

  const fromUrl = params.get("charge");
  const known = (id: string) => (source === "live" ? !!state.charges[id] : !!chargeDetail(id));
  const valid = fromUrl && known(fromUrl) ? fromUrl : null;
  // Desktop always shows a charge; C1 first because it arrives first and carries the split.
  const selected = valid ?? (isDesktop && (source === "fixture" || state.order.length > 0) ? (state.order[0] ?? "C1") : null);

  const select = useCallback(
    (id: string) => {
      lastRow.current = document.activeElement as HTMLElement | null;
      const url = `${pathname}?charge=${id}`;
      if (isDesktop) router.replace(url, { scroll: false });
      else {
        pushed.current = true;
        router.push(url, { scroll: false });
      }
    },
    [isDesktop, pathname, router],
  );

  const closeSheet = useCallback(() => {
    if (pushed.current) {
      pushed.current = false;
      router.back();
    } else router.replace(pathname, { scroll: false });
    requestAnimationFrame(() => lastRow.current?.focus());
  }, [pathname, router]);

  const sheetOpen = !isDesktop && !!selected;

  useEffect(() => {
    if (!sheetOpen) return;
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    sheetHeading.current?.focus();
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && closeSheet();
    window.addEventListener("keydown", onKey);
    return () => {
      document.body.style.overflow = prev;
      window.removeEventListener("keydown", onKey);
    };
  }, [sheetOpen, closeSheet]);

  const latest = state.feed[state.feed.length - 1];

  return (
    <MotionConfig reducedMotion="user">
      <div className="min-h-dvh" aria-hidden={sheetOpen || undefined} inert={sheetOpen || undefined}>
        <TopBar />
        <main className="mx-auto w-full max-w-[1320px] px-4 pt-5 pb-16 sm:px-6 lg:pt-8">
          {error && <p role="alert" className="mb-4 rounded-xl border border-dispute/40 bg-dispute-soft p-3 text-[16px]">{error}</p>}
          {awaitingPayment && <p role="status" className="mb-4 rounded-xl border border-line bg-panel p-3 text-[16px]">No run has started yet. Press “Northmart pays” on the home screen.</p>}
          <PaymentSummary remittance={state.run?.remittance ?? null} totals={state.totals} approval={state.approval} ledger={state.ledger} latest={latest} playing={state.playing} />

          <div className="mt-6 grid grid-cols-1 gap-6 lg:mt-8 lg:grid-cols-[minmax(0,26rem)_minmax(0,1fr)] lg:gap-8 xl:grid-cols-[minmax(0,28rem)_minmax(0,1fr)]">
            <div className="flex min-w-0 flex-col gap-6">
              <ChargeList state={state} selected={selected} onSelect={select} onAnswer={answerQuestion} onController={controllerDecides} />
              <ActivityFeed feed={state.feed} />
            </div>

            {isDesktop && selected && (
              <aside aria-label="Evidence" className="min-w-0">
                <div className="sticky top-6 max-h-[calc(100dvh-3rem)] overflow-y-auto rounded-2xl border border-line bg-panel p-7 [scrollbar-gutter:stable]">
                  <EvidencePanel key={selected} chargeId={selected} state={state} onAnswer={answerQuestion} />
                </div>
              </aside>
            )}
          </div>
        </main>
      </div>

      <AnimatePresence>
        {sheetOpen && selected && (
          <motion.div
            key="sheet"
            role="dialog"
            aria-modal="true"
            aria-label={`${selected} evidence`}
            className="fixed inset-0 z-40 overflow-y-auto overscroll-contain bg-panel"
            initial={{ x: "100%", opacity: 0.6 }}
            animate={{ x: 0, opacity: 1 }}
            exit={{ x: "100%", opacity: 0.6 }}
            transition={{ duration: 0.32, ease: [0.22, 1, 0.36, 1] }}
          >
            <div className="sticky top-0 z-10 flex h-14 items-center border-b border-line-soft bg-panel/95 px-2 backdrop-blur">
              <button type="button" onClick={closeSheet} className="flex items-center gap-1.5 rounded-lg px-2 py-2 text-[16px] font-semibold">
                <svg viewBox="0 0 16 16" width={16} height={16} aria-hidden>
                  <path d="M10 3 5 8l5 5" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
                </svg>
                All charges
              </button>
            </div>
            <div className="px-4 pt-5 pb-16">
              <EvidencePanel key={selected} chargeId={selected} state={state} onAnswer={answerQuestion} headingRef={sheetHeading} />
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </MotionConfig>
  );
}

function TopBar() {
  return (
    <header className="border-b border-line bg-panel/70">
      <div className="mx-auto flex h-14 w-full max-w-[1320px] items-center justify-between gap-3 px-4 sm:px-6">
        <div className="flex min-w-0 items-center gap-3">
          <span className="font-display text-[18px] font-extrabold tracking-[-0.02em]">Clawback</span>
          <span className="h-4 w-px bg-line" aria-hidden />
          <span className="truncate text-[15px] text-muted">{CAST.brand}</span>
        </div>
        <PrototypeBadge />
      </div>
    </header>
  );
}
