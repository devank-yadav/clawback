"use client";

// "Check for new payments": asks the connected sources now (POST /payments/sync) instead of waiting for their next
// look. A payment found starts its run, and the agents' live screen opens on it; otherwise "No new payments".

import { useRouter } from "next/navigation";
import { useState } from "react";
import { RefreshCw } from "lucide-react";
import * as api from "@/lib/api";
import { withAccount } from "@/lib/accounts";

export default function CheckPayments({ account }: { account: string | null | undefined }) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState<string | null>(null);

  async function check() {
    setBusy(true);
    setNote(null);
    try {
      const r = await api.syncPayments();
      const found = r.runs?.[0] ?? (r.run_id ? { run_id: r.run_id, account_id: r.account_id ?? account ?? "" } : null);
      if (found?.run_id) {
        router.push(withAccount("/", found.account_id || account, { run: found.run_id }));
        return;
      }
      setNote("No new payments");
    } catch (e) {
      setNote(`Couldn’t check just now (${(e as Error).message}).`);
    } finally {
      setBusy(false);
    }
  }

  return (
    <span className="ck">
      {note && <span className="ck-note" role="status">{note}</span>}
      <button className="cx-btn" onClick={() => void check()} disabled={busy}>
        <RefreshCw aria-hidden="true" className={busy ? "is-spinning" : undefined} />
        {busy ? "Checking…" : "Check for new payments"}
      </button>
    </span>
  );
}
