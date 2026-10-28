import { Inter } from "next/font/google";
import localFont from "next/font/local";

// The design system's two families: Fredoka for headlines (`--font-display`), Nunito for everything else (`--font-body`).
// Inter stays for the public site; inside the app (game-tokens.css) `--font-inter` points at Nunito.
export const inter = Inter({ subsets: ["latin"], variable: "--font-inter", display: "swap" });
export const fredoka = localFont({ src: "./fonts/Fredoka-Variable.woff2", weight: "300 700", variable: "--font-fredoka", display: "swap" });
export const nunito = localFont({ src: "./fonts/Nunito-Variable.woff2", weight: "200 1000", variable: "--font-nunito", display: "swap" });

export const fontVars = `${inter.variable} ${fredoka.variable} ${nunito.variable}`;
