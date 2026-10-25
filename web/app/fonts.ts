import { Fraunces, Inter } from "next/font/google";

// Inter for every UI word and number; Fraunces (a soft display serif) for page headlines only, through `.display`.
export const inter = Inter({ subsets: ["latin"], variable: "--font-inter", display: "swap" });
export const fraunces = Fraunces({ subsets: ["latin"], variable: "--font-fraunces", axes: ["opsz"], display: "swap" });

export const fontVars = `${inter.variable} ${fraunces.variable}`;
