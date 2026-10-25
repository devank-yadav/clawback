import { Inter } from "next/font/google";

// One font: Inter for every word and number. Headlines use it too, through `.display` (heavier, tighter).
export const inter = Inter({ subsets: ["latin"], variable: "--font-inter", display: "swap" });

export const fontVars = inter.variable;
