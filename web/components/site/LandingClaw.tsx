"use client";

// The hero explainer's last beat, once on load: the claw takes the money out of what the distributor deducted and
// drops it on the wrong part of the bar, the part disputed with proof. It draws over the explainer, which is complete
// without it; reduced motion shows no claw.

import { useState } from "react";
import { Claw, landPulse } from "@/components/ui/Claw";

export function LandingClaw() {
  const [frame, setFrame] = useState<HTMLElement | null>(null);
  const [done, setDone] = useState(false);
  return (
    <>
      <span hidden ref={(el) => setFrame(el?.parentElement ?? null)} />
      {!done && (
        <Claw host={frame} from=".hx-cut" to=".hx-bar .is-wrong" delay={1.6}
          onLand={() => landPulse(document.querySelector(".hx-legend .is-wrong"))}
          onDone={() => setDone(true)} />
      )}
    </>
  );
}
