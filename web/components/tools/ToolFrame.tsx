"use client";

import type { ReactNode } from "react";
import { Info } from "lucide-react";
import AppShell from "@/components/shell/AppShell";
import { PageHeader } from "@/components/ui/kit";
import { useCurrentAccount } from "@/lib/accounts";
import type { Account } from "@/lib/types";

/** The shell around the screens beside the workspace (Results, Next month, Deal coach, Try a clause, Audit log). */
export default function ToolFrame({ href, title, lead, children }: { href: string; title: string; lead: (account: Account) => string; children: (account: Account) => ReactNode }) {
  const { account, accounts, error } = useCurrentAccount();
  return (
    <AppShell account={account} accounts={accounts} active={href} crumb={title}>
      <main className="main-content tool-main">
        <PageHeader title={title} line={account ? lead(account) : undefined} />
        {error && <div className="feedback error" role="alert"><Info />{error}</div>}
        {!account && !error && <p className="muted" role="status">Loading your accounts…</p>}
        {account && <div key={account.id} className="tool-body">{children(account)}</div>}
      </main>
    </AppShell>
  );
}
