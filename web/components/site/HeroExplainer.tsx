// The landing hero's one-glance explainer: what Clawback does, in three pictures and almost no words.
//   1 the payment came in short · 2 every line checked against your contract · 3 the fair part accepted, the wrong
//   part disputed with proof, and the claw takes it back.
// The figures are the demo's own (Peak Bar Co.'s March payment from Northmart). It builds in once on load, about 1.5 s,
// left to right, in CSS (site.css, `--d` is each piece's delay), so the server's HTML and the browser agree; with
// reduced motion the build-in is off and it is simply there, finished.

import type { CSSProperties, ReactNode } from "react";
import { Bot, Check, Code2, MessageCircleQuestion } from "lucide-react";
import { LandingClaw } from "./LandingClaw";

const at = (seconds: number) => ({ "--d": `${seconds}s` }) as CSSProperties;

function Arrow({ delay }: { delay: number }) {
  return (
    <li className="hx-arrow" aria-hidden="true" style={at(delay)}>
      <svg viewBox="0 0 48 12" width="48" height="12"><path d="M1 6h44M40 1.5 45.5 6 40 10.5" /></svg>
    </li>
  );
}

function Step({ n, caption, delay, children }: { n: number; caption: string; delay: number; children: ReactNode }) {
  return (
    <li className="hx-step" style={at(delay)}>
      <span className="hx-n" aria-hidden="true">{n}</span>
      {children}
      <p className="hx-cap">{caption}</p>
    </li>
  );
}

export function HeroExplainer() {
  return (
    <div className="st-stage">
      <figure className="hx cw-host" aria-label="Your distributor paid $41,350 of $48,200 and deducted $6,850. Clawback checked every line against your contract: $2,730 is fair and accepted, $4,120 is wrong and disputed with proof, and one question comes to you.">
        <LandingClaw />
        <ol className="hx-steps">
          <Step n={1} caption="Your distributor pays short" delay={0}>
            <div className="hx-vis hx-stub">
              <span className="hx-tiny">Payment received</span>
              <strong className="hx-paid">$41,350</strong>
              <span className="hx-of">of $48,200 invoiced</span>
              <span className="hx-cut">−$6,850 deducted</span>
            </div>
          </Step>
          <Arrow delay={0.25} />
          <Step n={2} caption="Checked line by line against your contract" delay={0.4}>
            <div className="hx-vis hx-doc">
              <span className="hx-tiny">Your contract</span>
              <i style={{ width: "92%" }} /><i style={{ width: "78%" }} />
              <mark className="hx-hl">§3.2 Max 5,000 units</mark>
              <i style={{ width: "86%" }} /><i style={{ width: "60%" }} />
              <span className="hx-marks">
                <b className="is-ai"><Bot aria-hidden="true" />AI</b>
                <b className="is-code"><Code2 aria-hidden="true" />Code<Check aria-hidden="true" /></b>
              </span>
            </div>
          </Step>
          <Arrow delay={0.65} />
          <Step n={3} caption="The wrong part, claimed back" delay={0.8}>
            <div className="hx-vis hx-out">
              <span className="hx-tiny">The $6,850 taken</span>
              <div className="hx-bar">
                <i className="is-fair" style={{ flexGrow: 2730, ...at(0.95) }} />
                <i className="is-wrong" style={{ flexGrow: 4120, ...at(1.05) }} />
              </div>
              <ul className="hx-legend" style={at(1.15)}>
                <li className="is-fair"><b>$2,730</b> fair · accepted</li>
                <li className="is-wrong"><b>$4,120</b> wrong · disputed with proof</li>
              </ul>
              <span className="hx-q" style={at(1.3)}><MessageCircleQuestion aria-hidden="true" />1 question for you</span>
            </div>
          </Step>
        </ol>
      </figure>
    </div>
  );
}
