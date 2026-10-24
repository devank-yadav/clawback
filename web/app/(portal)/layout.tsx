import type { Metadata, Viewport } from "next";
import { IBM_Plex_Sans } from "next/font/google";
import "./portal.css";

const plex = IBM_Plex_Sans({ subsets: ["latin"], weight: ["400", "500", "600"], variable: "--font-plex", display: "swap" });

export const metadata: Metadata = {
  title: "Northmart Supplier Portal (fictional demo)",
  description: "Mock distributor portal for the Clawback demo. Northmart is a fictional company.",
};

export const viewport: Viewport = { width: "device-width", initialScale: 1 };

export default function PortalLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" className={plex.variable}>
      <body>{children}</body>
    </html>
  );
}
