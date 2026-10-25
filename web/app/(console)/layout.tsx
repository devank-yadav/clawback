import type { Metadata, Viewport } from "next";
import { Suspense, type ReactNode } from "react";
import { fontVars } from "../fonts";
import { RunProvider } from "@/components/console/RunProvider";
import "./console.css";
import "./flow.css";
import "../theme.css";
import "../billow.css";
import "../billow-pages.css";
import "../billow-tools.css";
import "../shell.css";
import "../app-pages.css";
import "../redesign.css";
import "../craft.css";

export const metadata: Metadata = {
  title: "Clawback — agents that win back what distributors wrongly took",
  description: "Six agents check every deduction against the signed contract. You stay in control.",
};

export const viewport: Viewport = { colorScheme: "light", themeColor: "#fcfdff" };

/** The console screens designed in Figma Make. One RunProvider keeps the same run across every page. */
export default function ConsoleLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en" className={fontVars}>
      <body>
        <Suspense fallback={null}>
          <RunProvider>{children}</RunProvider>
        </Suspense>
      </body>
    </html>
  );
}
