"use client";

// The app's one frame, on every page under /app: a finance-style left sidebar with the supplier's name, the
// distributor you're looking at (a switcher listing only this supplier's distributors, each with its plain status),
// the places (Agents, Distributors, History, Contracts, Saved, Connections), a Tools group, and the user menu with
// Sign out at the bottom. No top tab bar. On a phone the sidebar folds into a menu button. Signed-out visitors go to
// /signin and come back. Every link keeps the account in the URL (withAccount). The name TopBar stays so every page
// that rendered the old bar renders this frame unchanged.

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";
import {
  Bell, Bookmark, House, ChevronsUpDown, Gavel, ExternalLink, FileText, History as HistoryIcon,
  LogIn, LogOut, Menu, Plug, Truck, Workflow, X,
} from "lucide-react";
import { Logo } from "@/components/console/ui";
import { inkOn, withAccount } from "@/lib/accounts";
import { signOut, useSession } from "@/lib/session";
import { signInHref } from "@/lib/signin-route";
import * as api from "@/lib/api";
import type { Account, RelationshipStatus } from "@/lib/types";
import { useFetched } from "@/lib/useFetched";

type Item = { key: string; href: string; label: string; icon: ReactNode; view?: string };

const MAIN: Item[] = [
  { key: "home", href: "/app", label: "Home", icon: <House /> },
  { key: "agents", href: "/", label: "Agents", icon: <Workflow /> },
  { key: "distributors", href: "/distributors", label: "Distributors", icon: <Truck /> },
  { key: "history", href: "/history", label: "History", icon: <HistoryIcon /> },
  { key: "disputes", href: "/disputes", label: "Disputes", icon: <Gavel /> },
  { key: "contracts", href: "/contracts", label: "Contracts", icon: <FileText /> },
  { key: "saved", href: "/saved", label: "Saved", icon: <Bookmark /> },
  { key: "connections", href: "/connections", label: "Connections", icon: <Plug /> },
];

/** Which sidebar item the address is: /app → home, /app/history → history; a run's own pages are the agents'. */
function activeKey(path: string): string | null {
  if (path === "/app") return "home";
  const seg = path.replace(/^\/app\/?/, "").split("/")[0];
  if (["review", "activity", "approval", "upload"].includes(seg)) return "agents";
  return MAIN.some((i) => i.key === seg) ? seg : null;
}

/** Pages about the whole company, not one distributor: the switcher reads "All distributors" there. */
const COMPANY_WIDE = new Set(["/app", "/app/distributors"]);

export const STATUS_TONE: Record<RelationshipStatus, string> = {
  waiting_for_payment: "is-idle", checking: "is-live", needs_you: "is-amber", settled: "is-green", stopped: "is-red",
};

export function DistributorMark({ name, color, size = 28 }: { name: string; color?: string; size?: number }) {
  const bg = color ?? "#eaf2fe";
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

/** The distributor you're looking at, and the others this supplier tracks (GET /suppliers answers only the signed-in
 * supplier's), each with its plain status. */
function Switcher({ account, onPick }: { account: Account | null; onPick: () => void }) {
  const router = useRouter();
  const path = usePathname();
  const { supplier: mine } = useSession();
  const { open, setOpen, ref } = usePopover();
  const load = useCallback(() => api.fetchSuppliers(), []);
  const suppliers = useFetched(load, open ? "open" : "closed");
  const supplier = suppliers.data?.find((s) => s.distributors.some((d) => d.account_id === account?.id)) ?? null;
  const current = supplier?.distributors.find((d) => d.account_id === account?.id) ?? null;
  const allowed = mine ? new Set(mine.account_ids) : null;
  const tracked = supplier?.distributors.filter((d) => d.tracked && (!allowed || allowed.has(d.account_id))) ?? [];
  const all = COMPANY_WIDE.has(path);

  return (
    <div className="sb-switch" ref={ref}>
      <button className="sb-switch-btn" aria-haspopup="menu" aria-expanded={open} onClick={() => setOpen((v) => !v)} disabled={!account}>
        {all ? <span className="tb-mark sb-all" aria-hidden="true">∗</span> : <DistributorMark name={account?.distributor.name ?? "·"} color={account?.distributor.colors.primary} size={26} />}
        <span className="sb-switch-text">
          <small>Distributor</small>
          <strong>{all ? "All distributors" : account?.distributor.name ?? "Loading…"}</strong>
        </span>
        {current && !all && <i className={`tb-dot ${STATUS_TONE[current.status]}`} aria-label={current.status_label} />}
        <ChevronsUpDown aria-hidden="true" />
      </button>
      {open && (
        <div className="tb-menu sb-menu" role="menu">
          <span className="tb-menu-label">{supplier ? `${supplier.brand.name} sells through` : "Loading distributors…"}</span>
          {tracked.map((d) => (
            <button key={d.account_id} role="menuitemradio" aria-checked={!all && d.account_id === account?.id} className="tb-row"
              onClick={() => { setOpen(false); onPick(); router.push(withAccount(all ? "/" : path, d.account_id)); }}>
              <DistributorMark name={d.distributor.name} color={d.distributor.colors.primary} size={26} />
              <span><strong>{d.distributor.name}</strong><small>{d.status_label}</small></span>
              <i className={`tb-dot ${STATUS_TONE[d.status]}`} />
            </button>
          ))}
          <Link className="tb-menu-foot" href={withAccount("/distributors", account?.id)} onClick={() => { setOpen(false); onPick(); }}>Add or manage distributors</Link>
        </div>
      )}
    </div>
  );
}

const initials = (name: string) => name.split(/\s+/).filter(Boolean).map((p) => p[0]).join("").slice(0, 2).toUpperCase();

/** Who's signed in, with Sign out (and the page's own extras: account details, the demo reset). */
function UserMenu({ account, extra }: { account: Account | null; extra?: ReactNode }) {
  const { status, user } = useSession();
  const { open, setOpen, ref } = usePopover();
  const router = useRouter();
  if (status === "out" || status === "unknown") {
    return <Link className="sb-signin" href={signInHref(undefined)}><LogIn aria-hidden="true" /> Sign in</Link>;
  }
  // A laptop with no passwords: nobody signs in, the admin is the account's owner.
  const name = user?.name ?? account?.brand.owner.name ?? " ";
  const detail = user?.email ?? (status === "open" ? "Open laptop · no sign-in" : " ");
  return (
    <div className="sb-user" ref={ref}>
      <button className="sb-user-btn" aria-haspopup="menu" aria-expanded={open} onClick={() => setOpen((v) => !v)}>
        <i aria-hidden="true">{initials(name)}</i>
        <span><strong>{name}</strong><small>{detail}</small></span>
        <ChevronsUpDown aria-hidden="true" />
      </button>
      {open && (
        <div className="tb-menu sb-menu sb-user-menu" role="menu">
          {extra}
          {status === "in" && <button role="menuitem" className="tb-row" onClick={() => void signOut().then(() => router.push("/"))}><LogOut aria-hidden="true" /><span><strong>Sign out</strong></span></button>}
        </div>
      )}
    </div>
  );
}

const SEEN_KEY = "clawback:notifications-seen";
const readSeen = () => { try { return window.localStorage.getItem(SEEN_KEY) ?? ""; } catch { return ""; } };
const ago = (iso: string) => {
  const m = Math.max(0, Math.round((Date.now() - new Date(iso).getTime()) / 60000));
  return m < 1 ? "just now" : m < 60 ? `${m} min ago` : m < 1440 ? `${Math.round(m / 60)} h ago` : new Date(iso).toLocaleDateString("en-US", { month: "short", day: "numeric" });
};

/** What the supplier should know (GET /notifications: a distributor replied, a dispute went out), with a count of
 * what this browser hasn't opened yet. Looks again every 20 seconds while signed in. */
function Notifications({ account, onPick }: { account: Account | null; onPick: () => void }) {
  const { status } = useSession();
  const { open, setOpen, ref } = usePopover();
  const [tick, setTick] = useState(0);
  const [seen, setSeen] = useState<string | null>(null);
  const on = status === "in" || status === "open";
  const load = useCallback(() => api.fetchNotifications(), []);
  const list = useFetched(on ? load : null, String(tick));
  useEffect(() => {
    if (!on) return;
    const t = window.setInterval(() => setTick((n) => n + 1), 20_000);
    return () => window.clearInterval(t);
  }, [on]);
  if (!on) return null;
  const items = [...(list.data ?? [])].sort((a, b) => b.at.localeCompare(a.at));
  const lastSeen = seen ?? (typeof window === "undefined" ? "" : readSeen());
  const unread = items.filter((n) => n.at > lastSeen).length;
  const toggle = () => {
    setOpen((v) => !v);
    if (!open && items[0]) {
      try { window.localStorage.setItem(SEEN_KEY, items[0].at); } catch { /* remembered for this page only */ }
      setSeen(items[0].at);
    }
  };
  return (
    <div className="sb-bell" ref={ref}>
      <button className="sb-bell-btn" aria-haspopup="menu" aria-expanded={open} onClick={toggle}
        aria-label={unread ? `Notifications, ${unread} new` : "Notifications"}>
        <Bell aria-hidden="true" />
        {unread > 0 && <span className="sb-bell-count" aria-hidden="true">{unread > 9 ? "9+" : unread}</span>}
      </button>
      {open && (
        <div className="tb-menu sb-bell-menu" role="menu">
          <span className="tb-menu-label">Notifications</span>
          {items.length === 0 && <p className="sb-bell-empty">Nothing yet. Replies from distributors show up here.</p>}
          {items.slice(0, 12).map((n) => (
            <Link key={n.id} role="menuitem" className={`tb-row ${n.at > lastSeen ? "is-new" : ""}`} onClick={() => { setOpen(false); onPick(); }}
              href={n.dispute_id ? withAccount("/disputes", n.account_id, { id: n.dispute_id, ...(n.run_id ? { run: n.run_id } : {}) }) : withAccount("/", n.account_id ?? account?.id)}>
              <span><strong>{n.text}</strong><small>{ago(n.at)}</small></span>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}

/** Sends a signed-out visitor to /signin, and back here afterwards. */
function useSignedInOnly() {
  const { status } = useSession();
  useEffect(() => {
    if (status === "out") window.location.replace(signInHref(undefined, "needed"));
  }, [status]);
}

export default function TopBar({ account, extra }: { account: Account | null; active?: string; right?: ReactNode; extra?: ReactNode }) {
  const path = usePathname();
  const { supplier } = useSession();
  const [open, setOpen] = useState(false);
  useSignedInOnly();
  const active = activeKey(path);
  const close = () => setOpen(false);
  const supplierName = supplier?.name ?? account?.brand.name ?? " ";

  // The drawer closes on Escape; the page behind doesn't scroll while it's open.
  useEffect(() => {
    if (!open) return;
    const esc = (e: KeyboardEvent) => { if (e.key === "Escape") setOpen(false); };
    document.addEventListener("keydown", esc);
    document.body.classList.add("sb-locked");
    return () => { document.removeEventListener("keydown", esc); document.body.classList.remove("sb-locked"); };
  }, [open]);

  const link = (i: Item) => (
    <Link key={i.key} href={withAccount(i.href, account?.id)} className="sb-link" aria-current={active === i.key ? "page" : undefined} onClick={close}>
      {i.icon}<span>{i.label}</span>
    </Link>
  );

  return (
    <>
      <header className="sb-mobile">
        <button className="sb-menu-btn" aria-label="Open the menu" aria-expanded={open} aria-controls="sb" onClick={() => setOpen(true)}><Menu /></button>
        <Link href={withAccount("/app", account?.id)} className="sb-logo" aria-label="Clawback home"><Logo /> clawback</Link>
        <span className="sb-mobile-who">{account?.distributor.name ?? ""}</span>
      </header>
      {open && <div className="sb-backdrop" onClick={close} role="presentation" />}
      <aside id="sb" className={`sb ${open ? "is-open" : ""}`} aria-label="App">
        <div className="sb-head">
          <Link href={withAccount("/app", account?.id)} className="sb-logo" aria-label="Clawback home" onClick={close}><Logo /> clawback</Link>
          <span className="sb-head-right">
            <Notifications account={account} onPick={close} />
            <button className="sb-close" aria-label="Close the menu" onClick={close}><X /></button>
          </span>
        </div>
        <div className="sb-supplier">
          <i aria-hidden="true" style={account ? { background: account.brand.colors.primary, color: inkOn(account.brand.colors.primary) } : undefined}>{account?.brand.initials ?? initials(supplierName)}</i>
          <span><small>Supplier</small><strong>{supplierName}</strong></span>
        </div>
        <Switcher account={account} onPick={close} />
        <nav className="sb-nav" aria-label="Clawback">
          {MAIN.map(link)}
          {account && (
            <a className="sb-link" href={withAccount("/portal", account.id)} target="_blank" rel="noreferrer" onClick={close}>
              <ExternalLink /><span>{account.distributor.portal_name}</span>
            </a>
          )}
        </nav>
        <div className="sb-foot"><UserMenu account={account} extra={extra} /></div>
      </aside>
    </>
  );
}
