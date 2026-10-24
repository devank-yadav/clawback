import type { Metadata, Viewport } from "next";
import { IBM_Plex_Sans } from "next/font/google";
import "./portal.css";

const plex = IBM_Plex_Sans({ subsets: ["latin"], weight: ["400", "500", "600"], variable: "--font-plex", display: "swap" });

export const metadata: Metadata = {
  title: "Supplier portal · Deductions",
  description: "The distributor's side of a deduction dispute: the disputed lines, the thread and the reply box.",
};

export const viewport: Viewport = { width: "device-width", initialScale: 1 };

export default function PortalLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" className={plex.variable}>
      <body>{children}</body>
    </html>
  );
}
