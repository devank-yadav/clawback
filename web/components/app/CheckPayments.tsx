"use client";

// "Check for new payments": asks the connected sources now (POST /payments/sync) instead of waiting for their next
// look. One payment the agents started on opens straight away; several open Payments, where each one is listed. A
// payment found but not started (autopilot off) is shown as received, with "Run the agents"; otherwise "No new
// payments".

import { useRouter } from "next/navigation";
import { useState } from "react";
import { RefreshCw } from "lucide-react";
import * as api from "@/lib/api";
import { withAccount } from "@/lib/accounts";
import { RECEIVED_EVENT } from "@/components/app/ReceivedPayments";

export default function CheckPayments({ account }: { account: string | null | undefined }) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState<string | null>(null);

  async function check() {
    setBusy(true);
    setNote(null);
    try {
      const r = await api.syncPayments();
      const started = r.found.filter((f) => f.run_id);
      if (started.length > 1) {
        window.dispatchEvent(new Event(RECEIVED_EVENT));  // Payments, if it's open, looks again now
        setNote(`${started.length} new payments: the agents are on them.`);
        router.push(withAccount("/payments", account));
        return;
      }
      if (started[0]?.run_id) {
        router.push(withAccount("/", started[0].account_id || account, { run: started[0].run_id }));
        return;
      }
      if (r.found.length) {  // received: it waits for "Run the agents", which takes this button's place
        window.dispatchEvent(new Event(RECEIVED_EVENT));
        return;
      }
      setNote(r.message || "No new payments");
    } catch (e) {
      setNote(`Couldn’t check just now (${(e as Error).message}).`);
    } finally {
      setBusy(false);
    }
  }

  return (
    <span className="ck">
      {note && <span className="ck-note" role="status">{note}</span>}
      <button className="cx-btn is-blue" onClick={() => void check()} disabled={busy}>
        <RefreshCw aria-hidden="true" className={busy ? "is-spinning" : undefined} />
        {busy ? "Checking…" : "Check for new payments"}
      </button>
    </span>
  );
}
