import type { Metadata, Viewport } from "next";
import { Manrope } from "next/font/google";
import "./base.css";
import "./workspace.css";

const manrope = Manrope({ subsets: ["latin"], variable: "--font-manrope", display: "swap" });

export const metadata: Metadata = {
  title: "Clawback — Your payments, explained",
  description: "An evidence-first deduction review workspace for Peak Bar Co. Fictional interactive demo.",
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
