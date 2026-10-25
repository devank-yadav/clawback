"use client";

// The one bar on every page: the logo, the distributor you're looking at (a custom switcher showing each tracked
// distributor's plain status), the three places that matter (Agents, Distributors, Results) and a More menu for the
// rest. Everything keeps the account in the URL (withAccount).

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";
import { Logo } from "@/components/console/ui";
import { inkOn, withAccount } from "@/lib/accounts";
import { roleName } from "@/components/shell/SessionDialogs";
import { signOut, useSession } from "@/lib/session";
import * as api from "@/lib/api";
import type { Account, RelationshipStatus } from "@/lib/types";
import { useFetched } from "@/lib/useFetched";

const MAIN = [
  { key: "agents", href: "/", label: "Agents" },
  { key: "distributors", href: "/distributors", label: "Distributors" },
  { key: "history", href: "/history", label: "History" },
  { key: "saved", href: "/saved", label: "Saved" },
];

const MORE: { href: string; label: string; view?: string; hint: string }[] = [
  { href: "/contracts", label: "Contracts", hint: "The signed deal, locked, with what the agents read" },
  { href: "/connections", label: "Connections", hint: "Where payments, records and contracts come from" },
  { href: "/workspace", label: "Overview & payments", hint: "This distributor, every charge and its evidence" },
  { href: "/april", label: "Next month", hint: "The agents again, using your saved rules" },
  { href: "/coach", label: "Deal coach", hint: "Fixes for the next deal" },
  { href: "/scenario", label: "Try a clause", hint: "Paste a clause, watch the decision" },
];

export const STATUS_TONE: Record<RelationshipStatus, string> = {
  waiting_for_payment: "is-idle", checking: "is-live", needs_you: "is-amber", settled: "is-green", stopped: "is-red",
};

export function DistributorMark({ name, color, size = 28 }: { name: string; color?: string; size?: number }) {
  const bg = color ?? "#2b2d49";
  return <span className="tb-mark" style={{ background: bg, color: inkOn(bg), width: size, height: size, fontSize: size * 0.46 }} aria-hidden>{name.charAt(0)}</span>;
}

function usePopover() {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const close = (e: MouseEvent) => { if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false); };
    const esc = (e: KeyboardEvent) => { if (e.key === "Escape") setOpen(false); };
    document.addEventListener("mousedown", close);
    document.addEventListener("keydown", esc);
    return () => { document.removeEventListener("mousedown", close); document.removeEventListener("keydown", esc); };
  }, [open]);
  return { open, setOpen, ref };
}

/** The distributor you're looking at, and the others this supplier tracks, each with its plain status. */
function Switcher({ account }: { account: Account | null }) {
  const router = useRouter();
  const path = usePathname();
  const { open, setOpen, ref } = usePopover();
  const load = useCallback(() => api.fetchSuppliers(), []);
  const suppliers = useFetched(load, open ? "open" : "closed");
  const supplier = suppliers.data?.find((s) => s.distributors.some((d) => d.account_id === account?.id)) ?? null;
  const mine = supplier?.distributors.find((d) => d.account_id === account?.id) ?? null;
  const tracked = supplier?.distributors.filter((d) => d.tracked) ?? [];

  return (
    <div className="tb-switch" ref={ref}>
      <button className="tb-switch-btn" aria-haspopup="menu" aria-expanded={open} onClick={() => setOpen((v) => !v)} disabled={!account}>
        <DistributorMark name={account?.distributor.name ?? "·"} color={account?.distributor.colors.primary} />
        <span className="tb-switch-text">
          <small>{account?.brand.name ?? "Loading…"}</small>
          <strong>{account?.distributor.name ?? " "}</strong>
        </span>
        {mine && <i className={`tb-dot ${STATUS_TONE[mine.status]}`} aria-label={mine.status_label} />}
        <svg viewBox="0 0 24 24" aria-hidden="true"><path d="m7 10 5 5 5-5" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" /></svg>
      </button>
      {open && (
        <div className="tb-menu tb-switch-menu" role="menu">
          <span className="tb-menu-label">{supplier ? `${supplier.brand.name} sells through` : "Loading distributors…"}</span>
          {tracked.map((d) => (
            <button key={d.account_id} role="menuitemradio" aria-checked={d.account_id === account?.id} className="tb-row"
              onClick={() => { setOpen(false); router.push(withAccount(path === "/distributors" ? "/" : path, d.account_id)); }}>
              <DistributorMark name={d.distributor.name} color={d.distributor.colors.primary} size={26} />
              <span><strong>{d.distributor.name}</strong><small>{d.status_label}</small></span>
              <i className={`tb-dot ${STATUS_TONE[d.status]}`} />
            </button>
          ))}
          <Link className="tb-menu-foot" href={withAccount("/distributors", account?.id)} onClick={() => setOpen(false)}>Add or manage distributors</Link>
        </div>
      )}
    </div>
  );
}

function More({ account, extra }: { account: Account | null; extra?: ReactNode }) {
  const { open, setOpen, ref } = usePopover();
  return (
    <div className="tb-more" ref={ref}>
      <button className="tb-link" aria-haspopup="menu" aria-expanded={open} onClick={() => setOpen((v) => !v)}>More</button>
      {open && (
        <div className="tb-menu tb-more-menu" role="menu">
          {MORE.map((m) => (
            <Link key={m.label} role="menuitem" className="tb-row" href={withAccount(m.href, account?.id, m.view ? { view: m.view } : undefined)} onClick={() => setOpen(false)}>
              <span><strong>{m.label}</strong><small>{m.hint}</small></span>
            </Link>
          ))}
          {account && <a role="menuitem" className="tb-row" href={withAccount("/portal", account.id)} target="_blank" rel="noreferrer"><span><strong>{account.distributor.portal_name} ↗</strong><small>What the distributor sees</small></span></a>}
          {extra}
        </div>
      )}
    </div>
  );
}

/** Who's signed in, only once someone is: signing in happens when an action needs it (answer or approve). */
function Who({ account }: { account: Account | null }) {
  const { role } = useSession();
  if (!role || !account) return null;
  const name = roleName(role, account);
  return (
    <span className="tb-who">
      <i aria-hidden="true">{name.split(" ").map((p) => p[0]).join("").slice(0, 2)}</i>
      <span>{name}</span>
      <button onClick={signOut} title="Sign out" aria-label="Sign out">Sign out</button>
    </span>
  );
}

export default function TopBar({ account, active, extra }: { account: Account | null; active?: string; right?: ReactNode; extra?: ReactNode }) {
  return (
    <header className="tb">
      <Link href={withAccount("/", account?.id)} className="tb-logo"><Logo /> clawback</Link>
      <nav className="tb-nav" aria-label="Clawback">
        {MAIN.map((m) => (
          <Link key={m.key} href={withAccount(m.href, account?.id)} className="tb-link" aria-current={active === m.key ? "page" : undefined}>{m.label}</Link>
        ))}
        <More account={account} extra={extra} />
      </nav>
      <div className="tb-right">
        <Who account={account} />
        <Switcher account={account} />
      </div>
    </header>
  );
}
