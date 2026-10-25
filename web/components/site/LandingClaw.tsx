"use client";

// The landing page's example, once on load: the claw takes the overcharge out of the short payment and drops it on
// the Dispute chip. It sits inside the example frame and draws over it; the frame is complete without it.

import { useState } from "react";
import { Claw, landPulse } from "@/components/ui/Claw";

export function LandingClaw() {
  const [frame, setFrame] = useState<HTMLElement | null>(null);
  const [done, setDone] = useState(false);
  return (
    <>
      <span hidden ref={(el) => setFrame(el?.parentElement ?? null)} />
      {!done && (
        <Claw host={frame} from=".st-short" to=".st-check.is-dispute .st-chip" delay={0.6}
          onLand={() => landPulse(document.querySelector(".st-check.is-dispute .st-chip"))}
          onDone={() => setDone(true)} />
      )}
    </>
  );
}
