import { useReducedMotion } from "framer-motion";
import { createElement, useEffect, useRef, useState } from "react";
import type { CSSProperties, ReactNode } from "react";

export const EASE = [0.22, 1, 0.36, 1] as const;

/*
 * Entrance animations (pages, sections, list items) are CSS keyframes, not Framer Motion.
 * Framer drives animations from requestAnimationFrame and caps each frame's step, so when the
 * browser throttles frames (unfocused window, embedded preview pane) content that starts at
 * opacity 0 can stay invisible for seconds. CSS animations are time-based and always finish.
 */

/** Inline style for a CSS entrance delay, read by the `.a-*` animation classes. */
export const delay = (seconds: number): CSSProperties => ({ "--d": `${seconds}s` }) as CSSProperties;

type StaggerTag = "div" | "section" | "ul" | "ol";
type RiseTag = "div" | "section" | "li" | "aside" | "article";

/** Children rise in one after another (delays come from `.stagger > :nth-child(n)`). */
export function Stagger({ children, className = "", as = "div" }: { children: ReactNode; className?: string; as?: StaggerTag }) {
  return createElement(as, { className: `stagger ${className}`.trim() }, children);
}

/** A direct child of <Stagger>. */
export function Item({ children, className, as = "div" }: { children: ReactNode; className?: string; as?: RiseTag }) {
  return createElement(as, { className }, children);
}

/** Standalone entrance animation with an optional delay in seconds. */
export function Rise({ children, className = "", as = "div", delay: d = 0 }: { children: ReactNode; className?: string; as?: RiseTag; delay?: number }) {
  return createElement(as, { className: `a-rise ${className}`.trim(), style: delay(d) }, children);
}

const easeOutCubic = (t: number) => 1 - Math.pow(1 - t, 3);

/** Counts up to `value`. Progress is wall-clock based, so it lands on time even at a low frame rate. */
export function AnimatedNumber({ value, suffix = "", decimals = 0 }: { value: number | null | undefined; suffix?: string; decimals?: number }) {
  const reduce = useReducedMotion();
  const [shown, setShown] = useState(0);
  const from = useRef(0);

  useEffect(() => {
    if (value === null || value === undefined) return;
    const start = from.current;
    if (reduce || start === value) {
      from.current = value;
      setShown(value);
      return;
    }
    const t0 = performance.now();
    const duration = 900;
    let raf = 0;
    const tick = (now: number) => {
      const p = Math.min(1, (now - t0) / duration);
      const v = start + (value - start) * easeOutCubic(p);
      from.current = v;
      setShown(v);
      if (p < 1) raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    // Background tabs may never deliver another frame; make sure the real value always lands.
    const settle = window.setTimeout(() => {
      cancelAnimationFrame(raf);
      from.current = value;
      setShown(value);
    }, duration + 50);
    return () => {
      cancelAnimationFrame(raf);
      window.clearTimeout(settle);
    };
  }, [value, reduce]);

  if (value === null || value === undefined) return <span>—</span>;
  return <span>{`${shown.toFixed(decimals)}${suffix}`}</span>;
}

export function PageHeader({
  eyebrow,
  title,
  subtitle,
  actions,
  art,
}: {
  eyebrow?: ReactNode;
  title: ReactNode;
  subtitle?: ReactNode;
  actions?: ReactNode;
  art?: ReactNode;
}) {
  return (
    <header className={`page-hero ${art ? "has-art" : ""}`}>
      <div className="page-hero-text">
        {eyebrow && <div className="eyebrow">{eyebrow}</div>}
        <h1 className="a-rise">{title}</h1>
        {subtitle && <div className="page-hero-sub a-fade" style={delay(0.1)}>{subtitle}</div>}
        {actions && <div className="page-hero-actions a-fade" style={delay(0.15)}>{actions}</div>}
      </div>
      {art && <div className="page-hero-art a-pop" style={delay(0.08)} aria-hidden>{art}</div>}
    </header>
  );
}
