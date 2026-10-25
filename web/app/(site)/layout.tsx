import type { Metadata, Viewport } from "next";
import type { ReactNode } from "react";
import { fontVars } from "../fonts";
import "../theme.css";
import "./site.css";
import "../claw.css";

// The public pages: the landing page (/) and sign-in (/signin). No account, no run, no API calls until you sign in.

export const metadata: Metadata = {
  title: "Clawback · Get paid what the deal says",
  description: "Clawback checks every deduction your distributors take against the contract you signed, disputes the wrong ones with proof, and accepts the fair ones.",
};

export const viewport: Viewport = { colorScheme: "light", themeColor: "#fcfdff" };

export default function SiteLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en" className={fontVars}>
      <body className="st">{children}</body>
    </html>
  );
}
