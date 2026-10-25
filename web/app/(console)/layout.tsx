import type { Metadata, Viewport } from "next";
import { Suspense, type ReactNode } from "react";
import { Inter } from "next/font/google";
import { RunProvider } from "@/components/console/RunProvider";
import "./console.css";
import "./flow.css";

const inter = Inter({ subsets: ["latin"], variable: "--font-inter", display: "swap" });

export const metadata: Metadata = {
  title: "Clawback — agents that win back what distributors wrongly took",
  description: "Six agents check every deduction against the signed contract. You stay in control.",
};

export const viewport: Viewport = { colorScheme: "dark", themeColor: "#16171f" };

/** Run (`/`) and Distributors. One RunProvider follows the account's run across both. */
export default function ConsoleLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body className={inter.variable}>
        <Suspense fallback={null}>
          <RunProvider>{children}</RunProvider>
        </Suspense>
      </body>
    </html>
  );
}
