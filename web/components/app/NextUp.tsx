"use client";

// "What's next" once the page you're on has nothing left for you: the top item on the company's list (GET /overview,
// already ranked) from anywhere else, or "all caught up". It stays out of the way while this payment or dispute still
// needs you, so it only appears once you've done your part here.

import Link from "next/link";
import { useCallback, useEffect } from "react";
import { ArrowRight, Check } from "lucide-react";
import { withAccount } from "@/lib/accounts";
import * as api from "@/lib/api";
import type { NeedsYou } from "@/lib/types";
import { useFetched } from "@/lib/useFetched";

const VERB: Record<NeedsYou["kind"], string> = { question: "Answer", dispute_email: "Review and send", reply_email: "Answer them", approval: "Approve" };

function hrefOf(n: NeedsYou): string {
  if (n.link.page === "dispute" && n.link.dispute_id) return withAccount("/disputes", n.account_id, { id: n.link.dispute_id, ...(n.link.run_id ? { run: n.link.run_id } : {}) });
  return withAccount("/", n.account_id, n.link.run_id ? { run: n.link.run_id } : undefined);
}

/** `here`: the payment (run) or dispute on screen. `refresh` reloads the list (the page's own state moved on). */
export default function NextUp({ here, refresh = "", homeAccount }: { here: { runId?: string | null; disputeId?: string | null }; refresh?: string; homeAccount?: string }) {
  const load = useCallback(() => api.fetchCompanyOverview(), []);
  const o = useFetched(load, refresh);
  const { reload } = o;
  useEffect(() => {
    const t = window.setInterval(reload, 15_000);
    return () => window.clearInterval(t);
  }, [reload]);
  if (!o.data) return null;
  // A payment page counts everything from its run (its question, memo and dispute all show there); a dispute page
  // counts that dispute only.
  const isHere = (n: NeedsYou) => (!!here.disputeId && n.link.dispute_id === here.disputeId) || (!!here.runId && n.link.run_id === here.runId);
  if (o.data.needs_you.some(isHere)) return null;
  const next = o.data.needs_you[0];
  return (
    <aside className="cb-card nx" aria-label="What's next">
      {next ? (
        <>
          <span className="nx-label">Next for you{o.data.needs_you.length > 1 ? ` · ${o.data.needs_you.length} left` : ""}</span>
          <strong className="nx-title">{next.title}</strong>
          <Link className="cx-btn is-blue is-small nx-go" href={hrefOf(next)}>{VERB[next.kind]}<ArrowRight aria-hidden="true" /></Link>
        </>
      ) : (
        <>
          <span className="nx-done"><Check aria-hidden="true" /></span>
          <strong className="nx-title">You’re all caught up. The agents keep watching for payments and replies.</strong>
          <Link className="cx-btn is-ghost is-small nx-go" href={withAccount("/app", homeAccount)}>Home</Link>
        </>
      )}
    </aside>
  );
}
