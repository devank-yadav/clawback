"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import type { ReactNode } from "react";
import SessionDialogs from "@/components/shell/SessionDialogs";
import { Logo } from "./ui";
import { useRun } from "./RunProvider";

const I = {
  home: <path d="M3 10.5 12 3l9 7.5V21h-6v-6H9v6H3z" />,
  review: <><path d="M4 7V5a1 1 0 0 1 1-1h2M17 4h2a1 1 0 0 1 1 1v2M20 17v2a1 1 0 0 1-1 1h-2M7 20H5a1 1 0 0 1-1-1v-2" /><path d="M8 12h8" /></>,
  agents: <><circle cx="6" cy="6" r="2.5" /><circle cx="18" cy="18" r="2.5" /><path d="M8.5 6H14a4 4 0 0 1 0 8h-4a4 4 0 0 0 0 8" /></>,
  approval: <><path d="M4 4h12v16H4z" /><path d="M16 8h4v12h-4M8 9h4M8 13h4" /></>,
  audit: <><path d="M12 3 4 6v6c0 5 3.5 8 8 9 4.5-1 8-4 8-9V6z" /><path d="m9 12 2 2 4-4" /></>,
  more: <><path d="M4 6h16M4 12h16M4 18h10" /></>,
};
const icon = (d: ReactNode) => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    {d}
  </svg>
);

/** The workspace's other screens, so nothing the product does is out of reach from the console. */
const MORE = [
  { href: "/workspace", label: "Full workspace" },
  { href: "/upload", label: "Upload remittance" },
  { href: "/results", label: "Results" },
  { href: "/april", label: "Next month" },
  { href: "/coach", label: "Deal coach" },
  { href: "/scenario", label: "Try a clause" },
];

export function Shell({ crumbs, right, children }: { crumbs: string[]; right?: ReactNode; children: ReactNode }) {
  const path = usePathname();
  const router = useRouter();
  const { view, cast, account, accounts, link, error, accountsError } = useRun();
  const asking = view.stage === "owner" ? 1 : 0;
  const approving = view.approval?.status === "pending" ? 1 : 0;
  const controllerPage = path.startsWith("/approval");
  const items = [
    { href: "/", label: "Agents at work", d: I.agents, count: 0 },
    { href: "/home", label: "Home", d: I.home, count: 0 },
    { href: "/review", label: "Payment review", d: I.review, count: asking },
    { href: "/activity", label: "Agent activity", d: I.agents, count: 0 },
    { href: "/approval", label: "Controller approval", d: I.approval, count: approving },
  ];
  return (
    <div className="cx-shell">
      <aside className="cx-side" aria-label="Primary">
        <Link href={link("/")} className="cx-logo">
          <Logo /> clawback
        </Link>
        <label className="cx-org">
          <b>{account?.brand.initials?.[0] ?? cast.brand[0] ?? "·"}</b>
          {accounts && accounts.length > 1 ? (
            <select
              aria-label="Account"
              value={account?.id ?? ""}
              onChange={(e) => router.push(`${path}?account=${encodeURIComponent(e.target.value)}`)}
            >
              {accounts.map((a) => <option key={a.id} value={a.id}>{a.brand.name} ← {a.distributor.name}</option>)}
            </select>
          ) : cast.brand}
        </label>
        {items.map((it) => (
          <Link key={it.href} href={link(it.href)} className="cx-nav" aria-current={(it.href === "/" ? path === "/" : path.startsWith(it.href)) ? "page" : undefined}>
            {icon(it.d)}
            {it.label}
            {it.count > 0 && <span className="cx-count">{it.count}</span>}
          </Link>
        ))}
        <span className="cx-side-label">Workspace</span>
        <Link href={link("/audit")} className="cx-nav cx-side-extra">
          {icon(I.audit)}Audit trail
        </Link>
        <a href={link("/portal")} className="cx-nav cx-side-extra" target="_blank" rel="noreferrer">
          {icon(I.approval)}{cast.distributor} portal
        </a>
        {MORE.map((m) => (
          <Link key={m.href} href={link(m.href)} className="cx-nav cx-side-extra">
            {icon(I.more)}{m.label}
          </Link>
        ))}
        <div className="cx-side-foot">
          {controllerPage ? `${cast.controllerFull} · Controller` : `${cast.ownerFull} · Owner`}
          <small>{account ? `${account.distributor.name} · invoice ${account.invoice.id}` : " "}</small>
        </div>
      </aside>
      <div className="cx-main">
        <header className="cx-top">
          <nav aria-label="Breadcrumb">
            {crumbs.map((c) => (
              <span key={c}>{c}</span>
            ))}
          </nav>
          <span>{right ?? cast.brand}</span>
        </header>
        <main className="cx-page">
          {(error || accountsError) && <div className="cx-card" role="alert" style={{ color: "var(--amber)" }}>{accountsError ?? error}</div>}
          {children}
        </main>
      </div>
      <SessionDialogs account={account} />
    </div>
  );
}
