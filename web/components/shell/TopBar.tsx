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
  Landmark, Layers, LogIn, LogOut, Menu, MessagesSquare, Plug, RotateCcw, Truck, UserRound, Workflow, X,
} from "lucide-react";
import { Logo } from "@/components/console/ui";
import { inkOn, withAccount } from "@/lib/accounts";
import { askAdminToken, signOut, useSession } from "@/lib/session";
import { adminToken } from "@/lib/tokens";
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
        {all ? <span className="tb-mark sb-all" aria-hidden="true"><Layers /></span> : <DistributorMark name={account?.distributor.name ?? "·"} color={account?.distributor.colors.primary} size={26} />}
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

/** The presenter's controls, for a tab holding the admin token (lib/tokens.ts): the distributor's payment arrives
 * through the bank deposit exactly as in production (POST /payments/{account}), and the reset. Judges never see them. */
function usePresenter(account: Account | null) {
  const router = useRouter();
  const [note, setNote] = useState<string | null>(null);
  const simulate = useCallback(async () => {
    if (!account) return;
    setNote(`Posting ${account.distributor.name}’s payment…`);
    try {
      const paid = await api.accountPays(account.id);
      // Through the bank the run starts when the deposit is seen (about 5 s): find it, then open that run.
      let runId = paid.run_id;
      for (let i = 0; !runId && i < 20; i++) {
        await new Promise((r) => setTimeout(r, 1000));
        runId = (await api.latestRun(account.id))?.run_id ?? null;
      }
      setNote(null);
      router.push(withAccount("/", account.id, runId ? { run: runId } : undefined));
    } catch (e) {
      setNote(`The payment didn’t go through (${(e as Error).message}).`);
    }
  }, [account, router]);
  /** The distributor answers the newest dispute on its portal with a preset reply (the "no cap" claim when there is
   * one), the way a real reply arrives. The dispute goes out first (to the outbox, with no mail account) if it hasn't. */
  const reply = useCallback(async () => {
    if (!account) return;
    setNote(`${account.distributor.name} is replying…`);
    try {
      const threads = await api.fetchDisputes(account.id);
      const t = threads[0];
      if (!t) { setNote("No dispute to reply to yet."); return; }
      if (t.dispute.status === "ready_to_send" || t.dispute.status === "draft") {
        const email = await api.fetchDisputeEmail(t.dispute.id, t.run_id);
        await api.sendDispute(t.dispute.id, t.run_id, email.subject, email.body);
      }
      const presets = await api.fetchPortalPresets(account.id, t.dispute.id);
      const pick = presets.find((p) => p.id === "no-cap") ?? presets.find((p) => /cap/i.test(`${p.label} ${p.text}`)) ?? presets[0];
      if (!pick) { setNote("No reply to post."); return; }
      await api.postPortalMessage(t.dispute.id, pick.text, pick.attachment_doc_id);
      setNote(null);
      window.dispatchEvent(new Event("clawback:notify"));
      router.push(withAccount("/disputes", account.id, { id: t.dispute.id, run: t.run_id }));
    } catch (e) {
      setNote(`The reply didn’t go through (${(e as Error).message}).`);
    }
  }, [account, router]);
  const reset = useCallback(async () => {
    setNote("Resetting every distributor…");
    try {
      await api.resetWorkspace();
      window.location.reload();
    } catch (e) {
      setNote(`The reset didn’t go through (${(e as Error).message}).`);
    }
  }, []);
  // Alt+Shift+P: simulate the payment (asks for the admin token first when this tab has none).
  useEffect(() => {
    const key = (e: KeyboardEvent) => {
      if (!(e.altKey && e.shiftKey && e.code === "KeyP")) return;
      e.preventDefault();
      if (adminToken()) void simulate();
      else askAdminToken("Presenter mode: the admin token lets this tab post the distributor’s payment.", () => void simulate());
    };
    document.addEventListener("keydown", key);
    return () => document.removeEventListener("keydown", key);
  }, [simulate]);
  return { simulate, reply, reset, note };
}

/** Who's signed in. The menu opens upward with the account's details, the presenter's controls when this tab holds
 * the admin token, and Sign out. Enter or Space opens it, arrow keys and Tab move inside, Escape closes it. */
function UserMenu({ account }: { account: Account | null }) {
  const { status, user, supplier } = useSession();
  const [open, setOpen] = useState(false);
  const [details, setDetails] = useState(false);
  const wrap = useRef<HTMLDivElement>(null);
  const button = useRef<HTMLButtonElement>(null);
  const menu = useRef<HTMLDivElement>(null);
  const router = useRouter();
  const presenter = usePresenter(account);
  const [presenting, setPresenting] = useState(false);

  const close = useCallback((refocus = true) => {
    setOpen(false);
    setDetails(false);
    if (refocus) button.current?.focus();
  }, []);

  useEffect(() => {
    if (!open) return;
    // Focus the first item, keep Tab inside, Escape closes; a click outside closes without stealing focus.
    menu.current?.querySelector<HTMLElement>("[role=menuitem]")?.focus();
    const outside = (e: MouseEvent) => { if (wrap.current && !wrap.current.contains(e.target as Node)) close(false); };
    const key = (e: KeyboardEvent) => {
      if (e.key === "Escape") { e.preventDefault(); close(); return; }
      const items = [...(menu.current?.querySelectorAll<HTMLElement>("[role=menuitem]") ?? [])];
      if (!items.length) return;
      const at = items.indexOf(document.activeElement as HTMLElement);
      if (e.key === "ArrowDown" || (e.key === "Tab" && !e.shiftKey)) { e.preventDefault(); items[(at + 1) % items.length].focus(); }
      if (e.key === "ArrowUp" || (e.key === "Tab" && e.shiftKey)) { e.preventDefault(); items[(at - 1 + items.length) % items.length].focus(); }
    };
    document.addEventListener("mousedown", outside);
    document.addEventListener("keydown", key);
    return () => { document.removeEventListener("mousedown", outside); document.removeEventListener("keydown", key); };
  }, [open, close]);

  if (status === "out" || status === "unknown") {
    return <Link className="sb-signin" href={signInHref(undefined)}><LogIn aria-hidden="true" /> Sign in</Link>;
  }
  // A server with no passwords: nobody signs in, and the admin is the account's owner.
  const name = user?.name ?? account?.brand.owner.name ?? " ";
  const detail = user?.email ?? account?.brand.owner.email ?? " ";
  return (
    <div className="sb-user" ref={wrap}>
      <button ref={button} className="sb-user-btn" aria-haspopup="menu" aria-expanded={open} aria-controls="sb-user-menu" onClick={() => { if (open) close(); else { setPresenting(!!adminToken()); setOpen(true); } }}>
        <i aria-hidden="true">{initials(name)}</i>
        <span><strong>{name}</strong><small>{detail}</small></span>
        <ChevronsUpDown aria-hidden="true" />
      </button>
      {open && (
        <div id="sb-user-menu" ref={menu} className="tb-menu sb-user-menu" role="menu" aria-label="Your account">
          <button role="menuitem" className="tb-row" aria-expanded={details} onClick={() => setDetails((v) => !v)}><UserRound aria-hidden="true" /><span><strong>Account details</strong></span></button>
          {details && (
            <dl className="sb-details">
              <div><dt>Name</dt><dd>{name}</dd></div>
              <div><dt>Email</dt><dd>{detail}</dd></div>
              <div><dt>Company</dt><dd>{supplier?.name ?? account?.brand.name ?? " "}</dd></div>
              <div><dt>Role</dt><dd>Admin: answers the questions and approves what posts</dd></div>
            </dl>
          )}
          {presenting && account && (
            <>
              <button role="menuitem" className="tb-row" onClick={() => { close(false); void presenter.simulate(); }}><Landmark aria-hidden="true" /><span><strong>Presenter: simulate {account.distributor.name}’s payment</strong><small>Posts the bank deposit; the agents start on their own</small></span></button>
              <button role="menuitem" className="tb-row" onClick={() => { close(false); void presenter.reply(); }}><MessagesSquare aria-hidden="true" /><span><strong>Presenter: {account.distributor.name} replies to the dispute</strong><small>Posts their reply on the portal; you’re notified and the Negotiator answers</small></span></button>
              <button role="menuitem" className="tb-row" onClick={() => { close(false); void presenter.reset(); }}><RotateCcw aria-hidden="true" /><span><strong>Presenter: reset every distributor</strong></span></button>
            </>
          )}
          {status === "in" && <button role="menuitem" className="tb-row" onClick={() => void signOut().then(() => router.push("/"))}><LogOut aria-hidden="true" /><span><strong>Sign out</strong></span></button>}
        </div>
      )}
      {presenter.note && <p className="sb-note" role="status">{presenter.note}</p>}
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
    // Something just happened here (a reply posted): look again shortly, while the agents answer it.
    const soon = () => { window.setTimeout(() => setTick((n) => n + 1), 1500); window.setTimeout(() => setTick((n) => n + 1), 6000); };
    window.addEventListener("clawback:notify", soon);
    return () => { window.clearInterval(t); window.removeEventListener("clawback:notify", soon); };
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

export default function TopBar({ account }: { account: Account | null; active?: string; right?: ReactNode; extra?: ReactNode }) {
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
        <div className="sb-foot"><UserMenu account={account} /></div>
      </aside>
    </>
  );
}
