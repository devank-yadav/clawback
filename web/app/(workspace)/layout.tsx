import type { Metadata, Viewport } from "next";
import { Manrope } from "next/font/google";
import "./base.css";
import "./workspace.css";
import "./app.css";

const manrope = Manrope({ subsets: ["latin"], variable: "--font-manrope", display: "swap" });

export const metadata: Metadata = {
  title: "Clawback · Deductions, checked against the deal",
  description: "Clawback checks every deduction a distributor takes against the signed deal, disputes the wrong ones with proof and accepts the fair ones.",
};

export const viewport: Viewport = {
  colorScheme: "light",
  themeColor: "#fafaf9",
};

export default function WorkspaceLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" className="light">
      <body className={`${manrope.variable} antialiased`}>{children}</body>
    </html>
  );
}
