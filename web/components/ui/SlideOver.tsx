"use client";

// One overlay for the app: a panel that slides in from the right on a spring, over a blurred backdrop. Focus goes in,
// Tab stays inside, Escape or the backdrop closes it, and focus returns to what opened it. Reduced motion: it fades.

import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import { useEffect, useRef, useSyncExternalStore, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { X } from "lucide-react";

const noop = () => () => {};

export function SlideOver({ open, onClose, title, wide = false, children }: { open: boolean; onClose: () => void; title: ReactNode; wide?: boolean; children: ReactNode }) {
  const still = useReducedMotion();
  // Rendered into the body, so no transformed or blurred ancestor can trap the fixed panel inside itself.
  const mounted = useSyncExternalStore(noop, () => true, () => false);
  const panel = useRef<HTMLDivElement>(null);
  // The latest close handler, so a parent that passes a new function each render doesn't re-run the focus effect.
  const closeRef = useRef(onClose);
  useEffect(() => { closeRef.current = onClose; });
  useEffect(() => {
    if (!open) return;
    const back = document.activeElement as HTMLElement | null;
    const t = window.setTimeout(() => panel.current?.focus(), 30);
    const key = (e: KeyboardEvent) => {
      if (e.key === "Escape") { e.preventDefault(); closeRef.current(); return; }
      if (e.key !== "Tab" || !panel.current) return;
      const items = [...panel.current.querySelectorAll<HTMLElement>("button:not([disabled]), a[href], input, textarea, select, [tabindex='0']")];
      if (!items.length) return;
      const first = items[0], last = items[items.length - 1];
      if (e.shiftKey && (document.activeElement === first || document.activeElement === panel.current)) { e.preventDefault(); last.focus(); }
      else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
    };
    document.addEventListener("keydown", key);
    document.body.classList.add("so-locked");
    return () => { window.clearTimeout(t); document.removeEventListener("keydown", key); document.body.classList.remove("so-locked"); back?.focus?.(); };
  }, [open]);

  if (!mounted) return null;
  return createPortal(
    <AnimatePresence>
      {open && (
        <motion.div className="so-backdrop" onClick={onClose} role="presentation"
          initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} transition={{ duration: 0.2 }}>
          <motion.div ref={panel} className={`so-panel ${wide ? "is-wide" : ""}`} role="dialog" aria-modal="true" aria-label={typeof title === "string" ? title : undefined} tabIndex={-1}
            onClick={(e) => e.stopPropagation()}
            initial={still ? { opacity: 0 } : { x: "100%" }} animate={still ? { opacity: 1 } : { x: 0 }} exit={still ? { opacity: 0 } : { x: "100%" }}
            transition={still ? { duration: 0.15 } : { type: "spring", stiffness: 380, damping: 38 }}>
            <header className="so-head">
              <h2>{title}</h2>
              <button className="so-close" onClick={onClose} aria-label="Close"><X /></button>
            </header>
            <div className="so-body">{children}</div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>,
    document.body,
  );
}
