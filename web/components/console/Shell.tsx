"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import type { ReactNode } from "react";
import { CAST } from "@/lib/cast";
import { Logo } from "./ui";
import { useRun } from "./RunProvider";

const I = {
  home: <path d="M3 10.5 12 3l9 7.5V21h-6v-6H9v6H3z" />,
  review: <><path d="M4 7V5a1 1 0 0 1 1-1h2M17 4h2a1 1 0 0 1 1 1v2M20 17v2a1 1 0 0 1-1 1h-2M7 20H5a1 1 0 0 1-1-1v-2" /><path d="M8 12h8" /></>,
  agents: <><circle cx="6" cy="6" r="2.5" /><circle cx="18" cy="18" r="2.5" /><path d="M8.5 6H14a4 4 0 0 1 0 8h-4a4 4 0 0 0 0 8" /></>,
  approval: <><path d="M4 4h12v16H4z" /><path d="M16 8h4v12h-4M8 9h4M8 13h4" /></>,
  audit: <><path d="M12 3 4 6v6c0 5 3.5 8 8 9 4.5-1 8-4 8-9V6z" /><path d="m9 12 2 2 4-4" /></>,
};
const icon = (d: ReactNode) => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    {d}
  </svg>
);

export function Shell({ crumbs, right, children }: { crumbs: string[]; right?: ReactNode; children: ReactNode }) {
  const path = usePathname();
  const { view, source } = useRun();
  const asking = view.stage === "owner" ? 1 : 0;
  const approving = view.approval?.status === "pending" ? 1 : 0;
  const controllerPage = path.startsWith("/approval");
  const items = [
    { href: "/home", label: "Home", d: I.home, count: 0 },
    { href: "/review", label: "Payment review", d: I.review, count: asking },
    { href: "/activity", label: "Agent activity", d: I.agents, count: 0 },
    { href: "/approval", label: "Controller approval", d: I.approval, count: approving },
  ];
  return (
    <div className="cx-shell">
      <aside className="cx-side" aria-label="Primary">
        <Link href="/welcome" className="cx-logo">
          <Logo /> clawback
        </Link>
        <div className="cx-org">
          <b>P</b>
          {CAST.brand}
        </div>
        {items.map((it) => (
          <Link key={it.href} href={it.href} className="cx-nav" aria-current={path.startsWith(it.href) ? "page" : undefined}>
            {icon(it.d)}
            {it.label}
            {it.count > 0 && <span className="cx-count">{it.count}</span>}
          </Link>
        ))}
        <span className="cx-side-label">Workspace</span>
        <Link href="/audit" className="cx-nav cx-side-extra">
          {icon(I.audit)}Audit trail
        </Link>
        <Link href="/classic" className="cx-nav cx-side-extra">
          Classic workspace
        </Link>
        <div className="cx-side-foot">
          {controllerPage ? `${CAST.controllerFull} · Bookkeeper` : `${CAST.ownerFull} · Owner`}
          <small>Fictional demo · {source === "live" ? "live API" : "recorded run, no backend"}</small>
        </div>
      </aside>
      <div className="cx-main">
        <header className="cx-top">
          <nav aria-label="Breadcrumb">
            {crumbs.map((c) => (
              <span key={c}>{c}</span>
            ))}
          </nav>
          <span>{right ?? CAST.brand}</span>
        </header>
        <main className="cx-page">{children}</main>
      </div>
    </div>
  );
}
