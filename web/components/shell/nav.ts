// The app's one navigation, shared by the agents' flow (`/`) and the workspace and tool screens, so every page offers
// the same places in the same order. Links keep the account (withAccount).

export type NavItem = { href: string; label: string; view?: "overview" | "payments" | "approvals" | "rules" };

export const NAV: NavItem[] = [
  { href: "/", label: "Run" },
  { href: "/workspace", label: "Overview", view: "overview" },
  { href: "/workspace", label: "Payments", view: "payments" },
  { href: "/workspace", label: "Approvals", view: "approvals" },
  { href: "/workspace", label: "Rules", view: "rules" },
  { href: "/results", label: "Results" },
  { href: "/april", label: "Next month" },
  { href: "/coach", label: "Deal coach" },
  { href: "/scenario", label: "Try a clause" },
  { href: "/upload", label: "Upload" },
  { href: "/audit", label: "Audit" },
];
