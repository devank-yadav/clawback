"use client";

// The signature moment: the claw (the logo's ring and dot as its hub, two talons, a cable fading up) reaches in, grips
// a coin and pulls it back to where the money belongs, then lets go and lifts away. About 1.4 s, on springs, with a
// small lift before it plunges and a lagging swing while it carries. It plays over the content, never before it: the
// page is already there and usable, and the overlay takes no pointer events. Transforms and opacity only; the two
// points are measured once when it starts. Reduced motion: no claw at all, `onLand` fires at once.
//
// Two ways to play:
// - "pull": reach down onto `from`, grip, carry to `to`, drop (the run result, the landing page).
// - "drop": arrive above `to` already holding the coin, lower it, drop (Home's Recovered tile).

import { useAnimate, useReducedMotion } from "framer-motion";
import { useEffect, useRef, useState, useSyncExternalStore } from "react";
import { createPortal } from "react-dom";

type Point = { x: number; y: number };

/** Where the coin sits under the hub, in the rig's own coordinates. */
const SCALE = 1.3;
const GRIP_Y = 31 * SCALE;

function centerIn(el: Element, host: Element): Point {
  const a = el.getBoundingClientRect();
  const h = host.getBoundingClientRect();
  return { x: a.left - h.left + a.width / 2, y: a.top - h.top + a.height / 2 };
}

/** A gentle confirmation on the element the coin lands in: a quick swell and settle (transform only). */
export function landPulse(el: Element | null | undefined) {
  (el as HTMLElement | null)?.animate?.(
    [{ transform: "scale(1)" }, { transform: "scale(1.07)" }, { transform: "scale(1)" }],
    { duration: 360, easing: "cubic-bezier(0.16, 1, 0.3, 1)" },
  );
}

const noop = () => () => {};
const find = (x: Element | string | null | undefined) => (typeof x === "string" ? document.querySelector(x) : x ?? null);

export function Claw({ host, from, to, mode = "pull", label, tone = "dispute", delay = 0, maxWait, onLand, onDone }: {
  /** The positioned element the claw is drawn over; `from` and `to` are found inside the page. */
  host: HTMLElement | null;
  from?: Element | string | null;
  to: Element | string | null;
  mode?: "pull" | "drop";
  /** A short amount that rises from the landing spot, e.g. "$4,120". */
  label?: string;
  tone?: "dispute" | "good";
  /** Seconds to wait after the host comes into view. */
  delay?: number;
  /** Give up if the target isn't on screen within this many seconds: no claw, `onLand` and `onDone` fire, so a
   * figure held for the landing never waits on a scroll. */
  maxWait?: number;
  onLand?: () => void;
  onDone?: () => void;
}) {
  const still = useReducedMotion();
  const mounted = useSyncExternalStore(noop, () => true, () => false);
  const [scope, animate] = useAnimate();
  const [pts, setPts] = useState<{ a: Point; b: Point } | null>(null);
  const cb = useRef({ onLand, onDone });
  useEffect(() => { cb.current = { onLand, onDone }; });

  // Reduced motion: no claw; whatever waits on the landing happens now.
  useEffect(() => {
    if (!still) return;
    cb.current.onLand?.();
    cb.current.onDone?.();
  }, [still]);

  // Start only once the host is on screen (a result further down the page plays when it's reached), then measure.
  useEffect(() => {
    const target = find(to);
    if (still || !host || !target) return;
    let timer = 0;
    const giveUp = maxWait == null ? 0 : window.setTimeout(() => {
      io.disconnect();
      cb.current.onLand?.();
      cb.current.onDone?.();
    }, maxWait * 1000);
    const io = new IntersectionObserver((entries) => {
      if (!entries.some((e) => e.isIntersecting)) return;
      io.disconnect();
      window.clearTimeout(giveUp);
      timer = window.setTimeout(() => {
        const source = find(from);
        const b = centerIn(target, host);
        const a = mode === "pull" && source ? centerIn(source, host) : { x: b.x, y: b.y - 56 };
        setPts({ a, b });
      }, delay * 1000);
    }, { threshold: 0.6 });
    io.observe(target);
    return () => { io.disconnect(); window.clearTimeout(timer); window.clearTimeout(giveUp); };
  }, [still, host, to, from, mode, delay, maxWait]);

  useEffect(() => {
    if (!pts || !scope.current) return;
    let cancelled = false;
    const { a, b } = pts;
    const rig = scope.current.querySelector(".cw-rig") as HTMLElement;
    const left = scope.current.querySelector(".cw-l") as HTMLElement;
    const right = scope.current.querySelector(".cw-r") as HTMLElement;
    const coin = scope.current.querySelector(".cw-coin") as HTMLElement;
    const tag = scope.current.querySelector(".cw-tag") as HTMLElement | null;
    const hold = (p: Point) => ({ x: p.x, y: p.y - GRIP_Y });
    const open = () => Promise.all([animate(left, { rotate: 24 }, { duration: 0.14, ease: "easeOut" }), animate(right, { rotate: -24 }, { duration: 0.14, ease: "easeOut" })]);
    const close = () => Promise.all([animate(left, { rotate: -3 }, { duration: 0.13, ease: [0.3, 0, 0.2, 1] }), animate(right, { rotate: 3 }, { duration: 0.13, ease: [0.3, 0, 0.2, 1] })]);
    const swing = (dx: number) => Math.max(-9, Math.min(9, -dx / 28));

    (async () => {
      const start = hold(a);
      const pull = mode === "pull";
      // Set the stage: above the first point, talons open (or closed round the coin when it arrives holding it).
      await Promise.all([
        animate(rig, { x: start.x, y: start.y - 64, opacity: 0, rotate: 0 }, { duration: 0 }),
        animate(left, { rotate: pull ? 24 : -3 }, { duration: 0 }),
        animate(right, { rotate: pull ? -24 : 3 }, { duration: 0 }),
        animate(coin, { opacity: pull ? 0 : 1, scale: pull ? 0.5 : 1, y: 0 }, { duration: 0 }),
      ]);
      if (cancelled) return;
      // Anticipation: it appears and draws back a little before it reaches in.
      await animate(rig, { opacity: 1, y: start.y - 74 }, { duration: 0.14, ease: "easeOut" });
      if (pull) {
        await animate(rig, { y: start.y }, { type: "spring", stiffness: 520, damping: 30, mass: 0.8 });
        if (cancelled) return;
        // Grip: the coin comes up out of the figure as the talons close on it.
        await Promise.all([close(), animate(coin, { opacity: 1, scale: 1 }, { duration: 0.16, ease: [0.16, 1, 0.3, 1] })]);
      }
      if (cancelled) return;
      // Carry: lift, travel on a spring with a little overshoot, the rig swinging behind the motion and settling.
      const end = hold(b);
      const dx = end.x - start.x;
      animate(rig, { rotate: [0, swing(dx), 0] }, { duration: 0.62, ease: "easeInOut", times: [0, 0.35, 1] });
      await Promise.all([
        animate(rig, { x: end.x }, { type: "spring", stiffness: 170, damping: 19, mass: 0.9 }),
        pull
          ? animate(rig, { y: [null, Math.min(start.y, end.y) - 14, end.y] }, { duration: 0.58, ease: [0.33, 0, 0.2, 1], times: [0, 0.4, 1] })
          : animate(rig, { y: end.y }, { type: "spring", stiffness: 260, damping: 20, mass: 0.9 }),
      ]);
      if (cancelled) return;
      // Let go: the talons open and the coin drops into its place.
      await open();
      cb.current.onLand?.();
      animate(coin, { y: 14, scale: 0.6, opacity: 0 }, { duration: 0.22, ease: "easeIn" });
      if (tag) animate(tag, { opacity: [0, 1, 1, 0], y: [6, -10, -16, -22] }, { duration: 1.1, times: [0, 0.18, 0.7, 1], ease: "easeOut" });
      await animate(rig, { y: end.y - 70, opacity: 0 }, { duration: 0.34, ease: [0.4, 0, 1, 1], delay: 0.08 });
      if (!cancelled) cb.current.onDone?.();
    })();
    return () => { cancelled = true; };
  }, [pts, animate, scope, mode]);

  if (still || !mounted || !host) return null;
  return createPortal(
    <div ref={scope} className="cw" aria-hidden="true">
      {label && pts && <span className={`cw-tag is-${tone}`} style={{ left: pts.b.x + 26, top: pts.b.y - 30 }}>{label}</span>}
      <div className="cw-rig">
        <i className="cw-cable" />
        <div className="cw-body" style={{ scale: String(SCALE) }}>
          <span className="cw-l"><svg viewBox="0 0 24 40" width="24" height="40"><path d="M20 2 L10 10 Q7 12.5 7.4 16.5 L8.6 27 Q9 30 11.5 32 L16 34.5" /></svg></span>
          <span className="cw-r"><svg viewBox="0 0 24 40" width="24" height="40"><path d="M4 2 L14 10 Q17 12.5 16.6 16.5 L15.4 27 Q15 30 12.5 32 L8 34.5" /></svg></span>
          <span className="cw-hub">
            <svg viewBox="0 0 24 24" width="22" height="22">
              <circle cx="12" cy="12" r="10.5" className="cw-hub-plate" />
              <circle cx="12" cy="12" r="6.6" className="cw-hub-ring" strokeDasharray="31 10" />
              <circle cx="12" cy="12" r="2.4" className="cw-hub-dot" />
            </svg>
          </span>
          <span className="cw-coin"><b>$</b></span>
        </div>
      </div>
    </div>,
    host,
  );
}
