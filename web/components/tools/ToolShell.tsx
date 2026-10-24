import Link from "next/link";
import type { ReactNode } from "react";

const LINKS = [
  { href: "/", label: "Workspace" },
  { href: "/results", label: "Results" },
  { href: "/april", label: "April" },
  { href: "/coach", label: "Deal Coach" },
  { href: "/scenario", label: "Try a clause" },
  { href: "/audit", label: "Audit log" },
  { href: "/portal", label: "Northmart portal" },
];

/** Frame for the screens that sit beside the workspace: a plain header with links, then the page. */
export default function ToolShell({ title, lead, current, children }: { title: string; lead: string; current: string; children: ReactNode }) {
  return (
    <div className="tool">
      <header className="tool-top">
        <Link href="/" className="tool-word" aria-label="Clawback workspace">clawback<span>.</span></Link>
        <nav aria-label="Screens">
          {LINKS.map((l) => (
            <Link key={l.href} href={l.href} aria-current={l.href === current ? "page" : undefined}>{l.label}</Link>
          ))}
        </nav>
        <span className="tool-tag">Fictional demo</span>
      </header>
      <main className="tool-main">
        <div className="page-heading"><div><div className="eyebrow">Peak Bar Co.</div><h1>{title}</h1><p>{lead}</p></div></div>
        {children}
      </main>
    </div>
  );
}
