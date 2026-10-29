"use client";

// "Check for new payments": asks the connected bank and QuickBooks now (POST /payments/sync) instead of waiting for
// their next look. It only reports what they have, never a made-up payment. A payment found starts the agents in the
// background and you stay where you are: it shows on Payments (and Home), and opens only when you click it. One found
// but not started (autopilot off) is shown as received, with "Run the agents"; otherwise "No new payments".

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState } from "react";
import { RefreshCw } from "lucide-react";
import * as api from "@/lib/api";
import { withAccount } from "@/lib/accounts";
import { RECEIVED_EVENT } from "@/components/app/ReceivedPayments";

export default function CheckPayments({ account }: { account: string | null | undefined }) {
  const onPayments = usePathname().startsWith("/app/payments");
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState<string | null>(null);
  const [found, setFound] = useState(false);

  async function check() {
    setBusy(true);
    setNote(null);
    setFound(false);
    try {
      const r = await api.syncPayments();
      const started = r.found.filter((f) => f.run_id);
      if (r.found.length) window.dispatchEvent(new Event(RECEIVED_EVENT));  // Payments and Home look again now
      if (started.length) {
        setFound(true);
        setNote(started.length > 1 ? `${started.length} new payments: the agents are checking them.`
          : `${started[0].distributor} paid: the agents are checking it.`);
        return;
      }
      if (r.found.length) return;  // received: it waits for "Run the agents", which takes this button's place
      setNote(r.message || "No new payments");
    } catch (e) {
      setNote(`Couldn’t check just now (${(e as Error).message}).`);
    } finally {
      setBusy(false);
    }
  }

  return (
    <span className="ck">
      {note && (
        <span className="ck-note" role="status">
          {note}
          {found && !onPayments && <> <Link href={withAccount("/payments", account)}>See Payments</Link></>}
        </span>
      )}
      <button className="cx-btn is-blue" onClick={() => void check()} disabled={busy}>
        <RefreshCw aria-hidden="true" className={busy ? "is-spinning" : undefined} />
        {busy ? "Checking…" : "Check for new payments"}
      </button>
    </span>
  );
}
