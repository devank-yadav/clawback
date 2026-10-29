"use client";

// The app's one frame, on every page under /app: a finance-style left sidebar with six places
// (Home, Payments, Contracts, Disputes, Rules, Settings; every page lists all distributors and filters by one, so
// there is no distributor switcher), and the company's own menu (its mark and name, not a person's) with Sign out at
// the bottom. No top tab bar. On a phone the sidebar folds into a menu button. Signed-out visitors go to
// /signin and come back. Every link keeps the account in the URL (withAccount). The name TopBar stays so every page
// that rendered the old bar renders this frame unchanged.
//
// Payments start in the background, so the frame also says when the agents need you or have finished: Payments and
// Disputes carry a count of what's waiting on you there (GET /overview needs_you), and a note pops up on any page when
// a payment's check is done ("Northmart's payment is checked: 1 thing needs you"), with a link to it.

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import {
  Bell, BookCheck, Building2, FileText, House, ChevronsUpDown, Gavel, Settings as SettingsIcon, Wallet,
  KeyRound, Landmark, LogIn, LogOut, Menu, MessagesSquare, RotateCcw, X,
} from "lucide-react";
import { Logo } from "@/components/console/ui";
import { inkOn, withAccount } from "@/lib/accounts";
import { RECEIVED_EVENT } from "@/components/app/ReceivedPayments";
import { askAdminToken, signOut, useSession } from "@/lib/session";
import { adminToken } from "@/lib/tokens";
import { signInHref } from "@/lib/signin-route";
import * as api from "@/lib/api";
import type { Account, CompanyOverview, RelationshipStatus } from "@/lib/types";
import { useFetched } from "@/lib/useFetched";

type Item = { key: string; href: string; label: string; icon: ReactNode; view?: string };

const MAIN: Item[] = [
  { key: "home", href: "/app", label: "Home", icon: <House /> },
  { key: "payments", href: "/payments", label: "Payments", icon: <Wallet /> },
  { key: "contracts", href: "/contracts", label: "Contracts", icon: <FileText /> },
  { key: "disputes", href: "/disputes", label: "Disputes", icon: <Gavel /> },
  { key: "rules", href: "/rules", label: "Rules", icon: <BookCheck /> },
  { key: "settings", href: "/settings", label: "Settings", icon: <SettingsIcon /> },
];
/** Pages reached from Settings: the sidebar marks Settings while you're on one. */
const UNDER_SETTINGS = ["settings", "distributors", "connections"];

/** Which sidebar item the address is: /app → home, /app/payments → payments; a payment's own page (the agents' run) is Payments too. */
function activeKey(path: string): string | null {
  if (path === "/app") return "home";
  const seg = path.replace(/^\/app\/?/, "").split("/")[0];
  // a payment's own page (the agents' run) and the old History are Payments; the old Saved is Rules
  if (["review", "activity", "approval", "upload", "agents", "history", "payments"].includes(seg)) return "payments";
  if (seg === "saved") return "rules";
  if (UNDER_SETTINGS.includes(seg)) return "settings";
  return MAIN.some((i) => i.key === seg) ? seg : null;
}

export const STATUS_TONE: Record<RelationshipStatus, string> = {
  waiting_for_payment: "is-idle", checking: "is-live", needs_you: "is-amber", dispute_open: "is-info", settled: "is-green", stopped: "is-red",
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
const initials = (name: string) => name.split(/\s+/).filter(Boolean).map((p) => p[0]).join("").slice(0, 2).toUpperCase();

function usePresenter(account: Account | null) {
  const router = useRouter();
  const [note, setNote] = useState<string | null>(null);
  const simulate = useCallback(async () => {
    if (!account) return;
    setNote(`Posting ${account.distributor.name}’s payment…`);
    try {
      await api.accountPays(account.id);
      // The agents start in the background (through the bank, when the deposit is seen): the payment shows on
      // Payments and Home and opens only when clicked.
      window.dispatchEvent(new Event(RECEIVED_EVENT));
      setNote(`${account.distributor.name}’s payment arrived: the agents are checking it.`);
      window.setTimeout(() => setNote(null), 6_000);
    } catch (e) {
      setNote(`The payment didn’t go through (${(e as Error).message}).`);
    }
  }, [account]);
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
  // The reset answers once every distributor's history is back, so the reload opens on a full Home. This browser's
  // memory of announced payments and the recovered amount goes too, or an old "…'s payment is checked" note pops up.
  const [failed, setFailed] = useState(false);
  const reset = useCallback(async () => {
    setFailed(false);
    setNote("Resetting the demo…");
    const later = window.setTimeout(() => setNote("Getting every distributor ready…"), 1_200);
    try { window.sessionStorage.removeItem(DECIDED_KEY); } catch { /* nothing remembered */ }
    try { window.localStorage.removeItem(RECOVERED_SEEN_KEY); } catch { /* nothing remembered */ }
    let why: string;
    try {
      const r = await api.resetWorkspace();
      if (r.ok && r.ready) { window.location.reload(); return; }
      why = !r.ok ? `QuickBooks couldn’t be undone: ${r.error ?? "no reason given"}`
        : `the distributors’ history didn’t come back: ${r.story ?? "no reason given"}`;
    } catch (e) {
      why = (e as Error).message;
    } finally {
      window.clearTimeout(later);
    }
    setNote(`The reset didn’t finish (${why}).`);
    setFailed(true);
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
  return { simulate, reply, reset, note, failed };
}

/** The company using Clawback, not a person: its mark and name. The menu opens upward with the company's details,
 * the presenter's controls when this tab holds the admin token, and Sign out. Enter or Space opens it, arrow keys and Tab move inside, Escape closes it. */
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
  const company = supplier?.name ?? account?.brand.name ?? " ";
  // The sign-in, for the details only. A server with no passwords has none: the account's owner address stands in.
  const login = user?.email ?? account?.brand.owner.email ?? " ";
  const color = account?.brand.colors.primary;
  return (
    <div className="sb-user" ref={wrap}>
      <button ref={button} className="sb-user-btn" aria-haspopup="menu" aria-expanded={open} aria-controls="sb-user-menu" onClick={() => { if (open) close(); else { setPresenting(!!adminToken()); setOpen(true); } }}>
        <i aria-hidden="true" style={color ? { background: color, color: inkOn(color) } : undefined}>{account?.brand.initials ?? initials(company)}</i>
        <span><strong>{company}</strong><small>Supplier</small></span>
        <ChevronsUpDown aria-hidden="true" />
      </button>
      {open && (
        <div id="sb-user-menu" ref={menu} className="tb-menu sb-user-menu" role="menu" aria-label="Company account">
          <button role="menuitem" className="tb-row" aria-expanded={details} onClick={() => setDetails((v) => !v)}><Building2 aria-hidden="true" /><span><strong>Company details</strong></span></button>
          {details && (
            <dl className="sb-details">
              <div><dt>Company</dt><dd>{company}</dd></div>
              <div><dt>Signed in with</dt><dd>{login}</dd></div>
              <div><dt>Access</dt><dd>Admin: answers the questions and approves what posts</dd></div>
            </dl>
          )}
          <button role="menuitem" className="tb-row" onClick={() => { close(false); void presenter.reset(); }}><RotateCcw aria-hidden="true" /><span><strong>Reset the demo</strong><small>Every distributor back to the start, ready for the next payment</small></span></button>
          {!presenting && (
            <button role="menuitem" className="tb-row" onClick={() => { close(false); askAdminToken("Enter the presenter key. This tab then shows the presenter controls in your menu.", () => { setPresenting(true); setOpen(true); }); }}><KeyRound aria-hidden="true" /><span><strong>Presenter mode…</strong><small>Asks for the presenter key</small></span></button>
          )}
          {presenting && account && (
            <>
              <button role="menuitem" className="tb-row" onClick={() => { close(false); void presenter.simulate(); }}><Landmark aria-hidden="true" /><span><strong>Presenter: simulate {account.distributor.name}’s payment</strong><small>Posts the bank deposit; the agents start on their own</small></span></button>
              <button role="menuitem" className="tb-row" onClick={() => { close(false); void presenter.reply(); }}><MessagesSquare aria-hidden="true" /><span><strong>Presenter: {account.distributor.name} replies to the dispute</strong><small>Posts their reply on the portal; you’re notified and the Negotiator answers</small></span></button>
            </>
          )}
          {status === "in" && <button role="menuitem" className="tb-row" onClick={() => void signOut().then(() => router.push("/"))}><LogOut aria-hidden="true" /><span><strong>Sign out</strong></span></button>}
        </div>
      )}
      {presenter.note && (
        <p className="sb-note" role="status">
          {presenter.note}
          {presenter.failed && <> <button type="button" className="sb-retry" onClick={() => void presenter.reset()}>Try again</button></>}
        </p>
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
      <button className={`sb-bell-btn ${unread ? "is-ringing" : ""}`} aria-haspopup="menu" aria-expanded={open} onClick={toggle}
        aria-label={unread ? `Notifications, ${unread} new` : "Notifications"}>
        <Bell key={`bell-${unread}`} aria-hidden="true" />
        {unread > 0 && <span key={`count-${unread}`} className="sb-bell-count" aria-hidden="true">{unread > 9 ? "9+" : unread}</span>}
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

/** Which needs-you items each sidebar place counts: questions and memos are on a payment's page; dispute emails and
 * replies on Disputes. */
const COUNTED: Record<string, CompanyOverview["needs_you"][number]["kind"][]> = {
  payments: ["question", "approval"],
  disputes: ["dispute_email", "reply_email"],
};

// The payments already announced in this tab, so moving between pages doesn't announce them again, and one that
// finished while you were on another page is announced on the next.
const DECIDED_KEY = "clawback:decided-seen";
/** What Recovered showed the last time this browser saw Home (Dashboard.tsx); a reset forgets it with DECIDED_KEY. */
export const RECOVERED_SEEN_KEY = "clawback:recovered-seen";
const readDecided = (): Set<string> | null => {
  try { const raw = window.sessionStorage.getItem(DECIDED_KEY); return raw ? new Set(JSON.parse(raw) as string[]) : null; } catch { return null; }
};
const writeDecided = (ids: Set<string>) => {
  try { window.sessionStorage.setItem(DECIDED_KEY, JSON.stringify([...ids])); } catch { /* this page only */ }
};

type Finished = { runId: string; accountId: string; distributor: string; waiting: number };

/** GET /overview every 20 seconds while signed in (sooner after a payment arrives): the counts for the sidebar, and
 * the payment whose check just finished. */
function useWatch() {
  const { status } = useSession();
  const on = status === "in" || status === "open";
  const [tick, setTick] = useState(0);
  const [finished, setFinished] = useState<Finished | null>(null);
  // Each look also says whether a payment finished since the last one (the first look in a tab only learns what's there).
  const load = useCallback(async () => {
    const o = await api.fetchCompanyOverview();
    const decided = o.recent.filter((r) => r.kind === "run_decided" && r.link.run_id);
    const seen = readDecided();
    writeDecided(new Set([...(seen ?? []), ...decided.map((r) => r.link.run_id!)]));
    const r = seen ? decided.find((d) => !seen.has(d.link.run_id!)) : undefined;  // newest first
    if (r) setFinished({ runId: r.link.run_id!, accountId: r.account_id, distributor: r.distributor,
      waiting: o.needs_you.filter((n) => n.link.run_id === r.link.run_id).length });
    return o;
  }, []);
  const o = useFetched(on ? load : null, String(tick)).data;
  useEffect(() => {
    if (!on) return;
    const t = window.setInterval(() => setTick((n) => n + 1), 20_000);
    // A payment just arrived and the agents started on it: look again while they work.
    const soon = () => [5_000, 12_000, 25_000].forEach((ms) => window.setTimeout(() => setTick((n) => n + 1), ms));
    window.addEventListener(RECEIVED_EVENT, soon);
    return () => { window.clearInterval(t); window.removeEventListener(RECEIVED_EVENT, soon); };
  }, [on]);
  const counts = useMemo(() => Object.fromEntries(Object.entries(COUNTED).map(([key, kinds]) =>
    [key, o?.needs_you.filter((n) => kinds.includes(n.kind)).length ?? 0])), [o]);
  const dismiss = useCallback(() => setFinished(null), []);
  return { counts, finished, dismiss };
}

/** "Northmart's payment is checked", on whatever page you're on, for 12 seconds or until closed. */
function FinishedNote({ finished, onClose }: { finished: Finished | null; onClose: () => void }) {
  useEffect(() => {
    if (!finished) return;
    const t = window.setTimeout(onClose, 12_000);
    return () => window.clearTimeout(t);
  }, [finished, onClose]);
  if (!finished) return null;
  const { distributor, waiting } = finished;
  return (
    <div className="sb-toast" role="status">
      <span><strong>{distributor}’s payment is checked.</strong>{" "}
        {waiting ? `${waiting} thing${waiting === 1 ? " needs" : "s need"} you.` : "Nothing needs you."}</span>
      <Link className="cx-btn is-blue is-small" href={withAccount("/", finished.accountId, { run: finished.runId })} onClick={onClose}>See it</Link>
      <button className="sb-toast-x" aria-label="Close" onClick={onClose}><X aria-hidden="true" /></button>
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
  const watch = useWatch();
  const supplierName = supplier?.name ?? account?.brand.name ?? " ";

  // The drawer closes on Escape; the page behind doesn't scroll while it's open.
  useEffect(() => {
    if (!open) return;
    const esc = (e: KeyboardEvent) => { if (e.key === "Escape") setOpen(false); };
    document.addEventListener("keydown", esc);
    document.body.classList.add("sb-locked");
    return () => { document.removeEventListener("keydown", esc); document.body.classList.remove("sb-locked"); };
  }, [open]);

  const link = (i: Item) => {
    const n = watch.counts[i.key] ?? 0;
    return (
      <Link key={i.key} href={withAccount(i.href, account?.id)} className="sb-link" aria-current={active === i.key ? "page" : undefined} onClick={close}
        aria-label={n ? `${i.label}, ${n} waiting on you` : undefined}>
        {i.icon}<span>{i.label}</span>{n > 0 && <b className="sb-count" aria-hidden="true">{n > 9 ? "9+" : n}</b>}
      </Link>
    );
  };

  return (
    <>
      <header className="sb-mobile">
        <button className="sb-menu-btn" aria-label="Open the menu" aria-expanded={open} aria-controls="sb" onClick={() => setOpen(true)}><Menu /></button>
        <Link href={withAccount("/app", account?.id)} className="sb-logo" aria-label="Clawback home"><Logo /> clawback</Link>
        <span className="sb-mobile-who">{supplierName.trim()}</span>
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
        <nav className="sb-nav" aria-label="Clawback">
          {MAIN.map(link)}
        </nav>
        <div className="sb-foot"><UserMenu account={account} /></div>
      </aside>
      <FinishedNote finished={watch.finished} onClose={watch.dismiss} />
    </>
  );
}
