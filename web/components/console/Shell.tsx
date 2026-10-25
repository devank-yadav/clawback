"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import type { ReactNode } from "react";
import SessionDialogs from "@/components/shell/SessionDialogs";
import TopBar from "@/components/shell/TopBar";
import { useRun } from "./RunProvider";

const I = {
  home: <path d="M3 10.5 12 3l9 7.5V21h-6v-6H9v6H3z" />,
  review: <><path d="M4 7V5a1 1 0 0 1 1-1h2M17 4h2a1 1 0 0 1 1 1v2M20 17v2a1 1 0 0 1-1 1h-2M7 20H5a1 1 0 0 1-1-1v-2" /><path d="M8 12h8" /></>,
  agents: <><circle cx="6" cy="6" r="2.5" /><circle cx="18" cy="18" r="2.5" /><path d="M8.5 6H14a4 4 0 0 1 0 8h-4a4 4 0 0 0 0 8" /></>,
  approval: <><path d="M4 4h12v16H4z" /><path d="M16 8h4v12h-4M8 9h4M8 13h4" /></>,
};
const icon = (d: ReactNode) => (
  <svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    {d}
  </svg>
);

/** The console's pages (home, review, activity, approval) inside the app's frame: the sidebar (TopBar) holds every
 * place in the app, and these four sit as tabs above each page. */
export function Shell({ crumbs, right, children }: { crumbs: string[]; right?: ReactNode; children: ReactNode }) {
  const path = usePathname();
  const { view, cast, account, link, error, accountsError } = useRun();
  const asking = view.stage === "owner" ? 1 : 0;
  const approving = view.approval?.status === "pending" ? 1 : 0;
  const items = [
    { href: "/home", label: "Summary", d: I.home, count: 0 },
    { href: "/review", label: "Payment review", d: I.review, count: asking },
    { href: "/activity", label: "Agent activity", d: I.agents, count: 0 },
    { href: "/approval", label: "Your approval", d: I.approval, count: approving },
  ];
  return (
    <div className="cx-shell">
      <TopBar account={account} />
      <div className="cx-main">
        <header className="cx-top">
          <nav className="cx-tabs" aria-label="This payment">
            {items.map((it) => (
              <Link key={it.href} href={link(it.href)} aria-current={path === `/app${it.href}` ? "page" : undefined}>
                {icon(it.d)}
                {it.label}
                {it.count > 0 && <span className="cx-count">{it.count}</span>}
              </Link>
            ))}
          </nav>
          <span>{right ?? (crumbs.length ? crumbs.join(" / ") : cast.brand)}</span>
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
