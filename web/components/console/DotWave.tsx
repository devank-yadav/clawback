"use client";

// The intro's 3D dot wave (Figma: "Clawback · Intro" → "Agent wave"). A grid of points on a rolling sine surface,
// projected in perspective onto a 2D canvas: no WebGL or three.js needed, so nothing extra to install.
// Six agents ride the surface as glowing labelled points. Honors prefers-reduced-motion (draws one still frame).

import { useEffect, useRef } from "react";

const AGENTS: { name: string; u: number; v: number }[] = [
  { name: "Contract reader", u: 0.18, v: 0.3 },
  { name: "Second reader", u: 0.52, v: 0.18 },
  { name: "Investigator", u: 0.84, v: 0.38 },
  { name: "Calculator", u: 0.45, v: 0.52 },
  { name: "Policy check", u: 0.78, v: 0.72 },
  { name: "Negotiator", u: 0.22, v: 0.8 },
];

export function DotWave() {
  const wrap = useRef<HTMLDivElement>(null);
  const canvas = useRef<HTMLCanvasElement>(null);
  const labels = useRef<(HTMLSpanElement | null)[]>([]);

  useEffect(() => {
    const el = canvas.current;
    const box = wrap.current;
    if (!el || !box) return;
    const ctx = el.getContext("2d");
    if (!ctx) return;
    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const COLS = 72, ROWS = 46;
    let w = 0, h = 0, raf = 0;

    const resize = () => {
      const dpr = Math.min(window.devicePixelRatio || 1, 2);
      w = box.clientWidth;
      h = box.clientHeight;
      el.width = w * dpr;
      el.height = h * dpr;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    };

    // A point on the surface (u, v in 0..1) at time t, projected to screen space with a depth for size/alpha.
    const project = (u: number, v: number, t: number) => {
      const X = (u - 0.5) * 2.6;
      const Z = (v - 0.5) * 2.0;
      const Y = 0.16 * Math.sin(X * 2.2 + t * 0.6) + 0.12 * Math.cos(Z * 3.1 - t * 0.45) + 0.06 * Math.sin((X + Z) * 4 + t);
      // tilt the plane toward the viewer and turn it slowly
      const a = 0.35 + 0.08 * Math.sin(t * 0.1);
      const xr = X * Math.cos(a) - Z * Math.sin(a);
      const zr = X * Math.sin(a) + Z * Math.cos(a);
      const tilt = 1.0;
      const y2 = Y * Math.cos(tilt) - zr * Math.sin(tilt);
      const z2 = Y * Math.sin(tilt) + zr * Math.cos(tilt) + 3.2;
      const f = Math.min(w, h * 1.4) * 0.95;
      return { x: w * 0.52 + (xr * f) / z2, y: h * 0.5 + (y2 * f) / z2, d: 1 / z2 };
    };

    const draw = (ms: number) => {
      const t = reduce ? 4 : ms / 1000;
      ctx.clearRect(0, 0, w, h);
      for (let j = 0; j < ROWS; j++) {
        for (let i = 0; i < COLS; i++) {
          const p = project(i / (COLS - 1), j / (ROWS - 1), t);
          const edge = Math.min(i, COLS - 1 - i, j, ROWS - 1 - j) / 8;
          const alpha = Math.min(1, edge) * Math.min(1, (p.d - 0.2) * 3.2) * 0.75;
          if (alpha <= 0.02) continue;
          ctx.fillStyle = `rgba(161,163,180,${alpha.toFixed(3)})`;
          const r = 0.55 + p.d * 1.1;
          ctx.fillRect(p.x - r / 2, p.y - r / 2, r, r);
        }
      }
      AGENTS.forEach((ag, k) => {
        const p = project(ag.u, ag.v, t);
        const node = labels.current[k];
        if (node) node.style.transform = `translate(${p.x - 4}px, ${p.y - 8}px)`;
      });
      if (!reduce) raf = requestAnimationFrame(draw);
    };

    resize();
    const ro = new ResizeObserver(() => {
      resize();
      if (reduce) draw(0);
    });
    ro.observe(box);
    raf = requestAnimationFrame(draw);
    return () => {
      cancelAnimationFrame(raf);
      ro.disconnect();
    };
  }, []);

  return (
    <div className="cx-wave" ref={wrap} aria-hidden="true">
      <canvas ref={canvas} />
      {AGENTS.map((a, k) => (
        <span key={a.name} className="cx-wave-label" style={{ left: 0, top: 0 }} ref={(n) => { labels.current[k] = n; }}>
          <i />
          {a.name}
        </span>
      ))}
    </div>
  );
}
