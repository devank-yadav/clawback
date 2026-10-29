"use client";

// The brand: the claw-ring mark and the "clawback" wordmark as one lockup, in three sizes (styles: app/brand.css).
// The ring is the open claw, the dot the coin it closes on.
// - Arrival: on the first paint after a page load the ring draws itself in while it turns into place, then the coin
//   pops in (CSS keyframes, about 0.8 s). Once per page load: a client-side navigation that mounts it again shows it
//   at rest, so moving around the app doesn't replay it.
// - Hover or keyboard focus on the link around it: the claw turns once around the coin (Web Animations, so a quick
//   pass of the pointer still finishes the turn instead of snapping back).
// - Reduced motion: neither; the mark is drawn at rest from the first frame.

import { useEffect, useRef, useState } from "react";

export type BrandSize = "sm" | "md" | "lg";

/** Whether this page load has drawn the arrival yet. Module state: it survives client-side navigations, not reloads. */
let arrived = false;

const TURN: Keyframe[] = [{ transform: "rotate(0deg)" }, { transform: "rotate(360deg)" }];
const GRIP: Keyframe[] = [{ transform: "scale(1)" }, { transform: "scale(0.78)", offset: 0.45 }, { transform: "scale(1)" }];

export function BrandMark({ size = "md", animate = true }: {
  /** sm: the landing footer · md: the sidebar and the phone header · lg: sign-in and the landing header. */
  size?: BrandSize;
  /** false: always at rest, no arrival and no hover turn (a mark that isn't the page's brand moment). */
  animate?: boolean;
}) {
  const root = useRef<HTMLSpanElement>(null);
  const [arriving, setArriving] = useState(() => animate && !arrived);

  // The arrival runs from the first paint (the class is in the server HTML). Note it as played, then drop the class
  // once it has had time to finish, so a copy that was hidden at load (the phone header on a laptop) doesn't play it
  // later, when a resize shows it.
  useEffect(() => {
    if (!arriving) return;
    arrived = true;
    const t = window.setTimeout(() => setArriving(false), 1500);
    return () => window.clearTimeout(t);
  }, [arriving]);

  useEffect(() => {
    const el = root.current;
    const link = el?.closest<HTMLElement>("a, button");
    const ring = el?.querySelector<SVGCircleElement>(".cb-brand-ring");
    const dot = el?.querySelector<SVGCircleElement>(".cb-brand-dot");
    if (!animate || !link || !ring || !dot) return;
    const turn = (e: Event) => {
      if (e.type === "focus" && !link.matches(":focus-visible")) return;
      if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
      if (ring.getAnimations().some((a) => a.playState === "running")) return;
      ring.animate(TURN, { duration: 600, easing: "cubic-bezier(0.65, 0, 0.35, 1)" });
      dot.animate(GRIP, { duration: 600, easing: "ease-in-out" });
    };
    link.addEventListener("pointerenter", turn);
    link.addEventListener("focus", turn);
    return () => {
      link.removeEventListener("pointerenter", turn);
      link.removeEventListener("focus", turn);
    };
  }, [animate]);

  return (
    <span ref={root} className={`cb-brand is-${size}${arriving ? " is-arriving" : ""}`}>
      <svg className="cb-brand-mark" viewBox="2 2 20 20" width="1em" height="1em" aria-hidden="true">
        <circle className="cb-brand-ring" cx="12" cy="12" r="9" fill="none" stroke="#777cff" strokeWidth="2.4" strokeLinecap="round" strokeDasharray="44 100" />
        <circle className="cb-brand-dot" cx="12" cy="12" r="3" fill="#777cff" />
      </svg>
      <span className="cb-brand-word">clawback</span>
    </span>
  );
}
