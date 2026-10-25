"use client";

import type { ReactNode } from "react";
import { Info } from "lucide-react";
import AppShell from "@/components/shell/AppShell";
import type { Place } from "@/components/shell/TopBar";
import { useCurrentAccount } from "@/lib/accounts";
import type { Account } from "@/lib/types";

/** The shell around the screens beside the run: Records and Results, and the More tools (Next month, Deal coach, Try a
 * clause). */
export default function ToolFrame({ place, title, lead, children }: { place?: Place; title: string; lead: (account: Account) => string; children: (account: Account) => ReactNode }) {
  const { account, accounts, error } = useCurrentAccount();
  return (
    <AppShell account={account} accounts={accounts} active={place} crumb={title}>
      <main className="main-content tool-main">
        <div className="page-heading"><div><div className="eyebrow">{account?.brand.name ?? " "}</div><h1>{title}</h1>{account && <p>{lead(account)}</p>}</div></div>
        {error && <div className="feedback error" role="alert"><Info />{error}</div>}
        {!account && !error && <p className="muted" role="status">Loading your accounts…</p>}
        {account && <div key={account.id} className="tool-body">{children(account)}</div>}
      </main>
    </AppShell>
  );
}
