"use client";

// A run's audit trail, opened from its result as a slide-over: every action on this run, who or what took it, and
// whether the hash chain is intact (GET /audit?run_id=, GET /audit/verify).

import { useCallback } from "react";
import { CircleCheck, CircleX } from "lucide-react";
import { SlideOver } from "@/components/ui/SlideOver";
import * as api from "@/lib/api";
import type { AuditEntry } from "@/lib/types";
import { useFetched } from "@/lib/useFetched";

const when = (iso: string) => new Date(iso).toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit", second: "2-digit" });
const ACTOR: Record<string, string> = { gate: "Rules", negotiator: "Negotiator", bookkeeper: "Bookkeeper", owner: "You", investigator: "Investigator", reader: "Deal readers" };

/** "decision split" → "Decision split"; "charge:C1" → "C1". */
const plain = (e: AuditEntry) => {
  const [verb, ...rest] = e.action.split(/[\s_]+/);
  const what = e.object_ref.replace(/^[a-z_]+:/, "");
  return `${verb.charAt(0).toUpperCase()}${verb.slice(1)}${rest.length ? ` ${rest.join(" ")}` : ""} · ${what}`;
};

function Entries({ runId }: { runId: string }) {
  const load = useCallback(() => Promise.all([api.fetchRunAudit(runId), api.verifyAudit()]), [runId]);
  const fetched = useFetched(load);
  const entries = fetched.data?.[0] ?? [];
  const verify = fetched.data?.[1] ?? null;
  return (
    <>
      {verify && (
        <p className={`ad-verify ${verify.ok ? "is-ok" : "is-broken"}`}>
          {verify.ok ? <CircleCheck aria-hidden="true" /> : <CircleX aria-hidden="true" />}
          {verify.ok ? `Chain intact · ${verify.checked} entries checked` : `Chain broken at entry ${verify.broken_at}: ${verify.reason}`}
        </p>
      )}
      {fetched.error && <p className="fl-problem" role="alert">{fetched.error}</p>}
      {!fetched.data && !fetched.error && <p className="ad-empty" role="status">Loading the entries…</p>}
      {fetched.data && entries.length === 0 && <p className="ad-empty">No entries for this run yet.</p>}
      <ol className="ad-list">
        {entries.map((e) => (
          <li key={e.id}>
            <span className="ad-what">{plain(e)}</span>
            <span className="ad-meta">{ACTOR[e.actor] ?? e.actor} · {when(e.at)}</span>
            <code className="ad-hash" title={e.hash}>{e.hash.slice(0, 10)}</code>
          </li>
        ))}
      </ol>
    </>
  );
}

export function AuditDrawer({ runId, open, onClose }: { runId: string; open: boolean; onClose: () => void }) {
  return (
    <SlideOver open={open} onClose={onClose} title="Audit trail">
      {open && <Entries runId={runId} />}
    </SlideOver>
  );
}
