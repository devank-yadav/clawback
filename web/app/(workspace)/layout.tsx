import type { Metadata, Viewport } from "next";
import { fontVars } from "../fonts";
import "./base.css";
import "./workspace.css";
import "./app.css";
import "../(console)/console.css";
import "../(console)/flow.css";
import "./unify.css";
import "../theme.css";
import "../billow.css";
import "../billow-pages.css";
import "../billow-tools.css";
import "../shell.css";
import "../app-pages.css";
import "../redesign.css";

// One app with the agents' flow at `/`: the same tokens (theme.css), the same parts (flow.css) and the same type.

export const metadata: Metadata = {
  title: "Clawback · Deductions, checked against the deal",
  description: "Clawback checks every deduction a distributor takes against the signed deal, disputes the wrong ones with proof and accepts the fair ones.",
};

export const viewport: Viewport = {
  colorScheme: "light",
  themeColor: "#fcfdff",
};

export default function WorkspaceLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" className={fontVars}>
      <body className="antialiased">{children}</body>
    </html>
  );
}
