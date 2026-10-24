import type { Metadata, Viewport } from "next";
import { Inter } from "next/font/google";
import "./base.css";
import "./workspace.css";
import "./app.css";
import "../(console)/console.css";
import "../(console)/flow.css";
import "./unify.css";

// One app with the agents' flow at `/`: the same tokens (console.css), the same parts (flow.css) and the same type.
const inter = Inter({ subsets: ["latin"], variable: "--font-inter", display: "swap" });

export const metadata: Metadata = {
  title: "Clawback · Deductions, checked against the deal",
  description: "Clawback checks every deduction a distributor takes against the signed deal, disputes the wrong ones with proof and accepts the fair ones.",
};

export const viewport: Viewport = {
  colorScheme: "dark",
  themeColor: "#16171f",
};

export default function WorkspaceLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" className="dark">
      <body className={`${inter.variable} antialiased`}>{children}</body>
    </html>
  );
}
