"use client";

// A run's audit trail, opened from its result: every action on this run, who or what took it, and whether the hash
// chain is intact (GET /audit?account=, filtered to the run; GET /audit/verify). It replaces the separate Audit page.

import { useCallback, useEffect, useRef } from "react";
import { CircleCheck, CircleX, X } from "lucide-react";
import * as api from "@/lib/api";
import type { AuditEntry } from "@/lib/types";
import { useFetched } from "@/lib/useFetched";

const when = (iso: string) => new Date(iso).toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit", second: "2-digit" });
const ACTOR: Record<string, string> = { gate: "Rules", negotiator: "Negotiator", bookkeeper: "Bookkeeper", owner: "You", investigator: "Investigator", reader: "Deal readers" };

/** "decision split" → "Decision: split"; "charge:C1" → "C1". */
const plain = (e: AuditEntry) => {
  const [verb, ...rest] = e.action.split(/[\s_]+/);
  const what = e.object_ref.replace(/^[a-z_]+:/, "");
  return `${verb.charAt(0).toUpperCase()}${verb.slice(1)}${rest.length ? ` ${rest.join(" ")}` : ""} · ${what}`;
};

export function AuditDrawer({ runId, onClose }: { runId: string; onClose: () => void }) {
  const panel = useRef<HTMLDivElement>(null);
  const load = useCallback(() => Promise.all([api.fetchRunAudit(runId), api.verifyAudit()]), [runId]);
  const fetched = useFetched(load);
  const entries = fetched.data?.[0] ?? [];
  const verify = fetched.data?.[1] ?? null;

  // A dialog: focus goes in, Escape closes it, and Tab stays inside until it does.
  useEffect(() => {
    const el = panel.current;
    el?.focus();
    const key = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
      if (e.key !== "Tab" || !el) return;
      const items = [...el.querySelectorAll<HTMLElement>("button, a[href]")];
      if (!items.length) return;
      const first = items[0], last = items[items.length - 1];
      if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
      else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
    };
    document.addEventListener("keydown", key);
    return () => document.removeEventListener("keydown", key);
  }, [onClose]);

  return (
    <div className="ad-backdrop" onClick={onClose} role="presentation">
      <div ref={panel} className="ad-panel" role="dialog" aria-modal="true" aria-labelledby="ad-title" tabIndex={-1} onClick={(e) => e.stopPropagation()}>
        <header className="ad-head">
          <h2 id="ad-title">Audit trail</h2>
          <button className="ad-close" onClick={onClose} aria-label="Close the audit trail"><X /></button>
        </header>
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
      </div>
    </div>
  );
}
