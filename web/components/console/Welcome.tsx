"use client";

import Link from "next/link";
import { useRun } from "./RunProvider";
import { DotWave } from "./DotWave";
import { Logo } from "./ui";

/** Intro (Figma: "Clawback · Intro"): the opening shot of the demo. */
export default function Welcome() {
  const { cast, link } = useRun();
  return (
    <div className="cx-intro">
      <DotWave />
      <header className="cx-intro-top">
        <Link href={link("/welcome")} className="cx-logo" style={{ padding: 0 }}>
          <Logo size={24} /> clawback
        </Link>
        <span>{cast.brand} / Your recovery workspace</span>
      </header>
      <section className="cx-intro-copy">
        <span className="cx-eyebrow">Small food brands. Every dollar matters.</span>
        <h1>Get back the money distributors wrongly took.</h1>
        <p>Six agents check the evidence. You stay in control.</p>
        <div>
          <Link className="cx-btn" href={link("/review")}>
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true"><path d="M7 4v16l13-8z" /></svg>
            Watch the agents work
          </Link>
        </div>
        <span className="cx-tiny">Grounded in your contracts. Nothing sent without you.</span>
      </section>
      <footer className="cx-intro-foot">
        <span>Read. Verify. Calculate. Recover.</span>
        <span>Built for your books. Accountable to you.</span>
      </footer>
    </div>
  );
}
