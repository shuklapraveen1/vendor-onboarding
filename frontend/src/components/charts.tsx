import { useMemo } from "react";
import type { CSSProperties, ReactNode } from "react";
import { STATUS_META, riskTone } from "../lib";
import type { Status, Submission } from "../types";
import { AnimatedNumber, delay } from "./motion";

const TONE_VAR: Record<string, string> = {
  green: "var(--green)",
  amber: "var(--amber)",
  violet: "var(--violet)",
  red: "var(--red)",
  blue: "var(--blue)",
  gray: "var(--muted)",
};

export const toneColor = (tone: string) => TONE_VAR[tone] ?? TONE_VAR.gray;

/* ------------------------------------------------------------------ donut */

export function StatusDonut({
  counts,
  order,
  active,
  onSelect,
  centerLabel = "submissions",
}: {
  counts: Partial<Record<Status, number>>;
  order: Status[];
  active?: string;
  onSelect?: (s: Status) => void;
  centerLabel?: string;
}) {
  const size = 168;
  const stroke = 18;
  const r = (size - stroke) / 2;
  const c = 2 * Math.PI * r;
  const total = order.reduce((n, s) => n + (counts[s] ?? 0), 0);
  let offset = 0;
  const segments = order
    .map((s) => ({ status: s, value: counts[s] ?? 0 }))
    .filter((s) => s.value > 0)
    .map((s) => {
      const len = (s.value / total) * c;
      const gap = total > s.value ? Math.min(4, len / 3) : 0;
      const seg = { ...s, len: Math.max(len - gap, 0.5), offset };
      offset += len;
      return seg;
    });

  return (
    <div className="donut">
      <div className="donut-chart" style={{ width: size, height: size }}>
        <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} role="img" aria-label="Submissions by status">
          <circle cx={size / 2} cy={size / 2} r={r} fill="none" style={{ stroke: "var(--surface-3)" }} strokeWidth={stroke} />
          <g transform={`rotate(-90 ${size / 2} ${size / 2})`}>
            {segments.map((s, i) => (
              <circle
                key={s.status}
                className="donut-seg"
                cx={size / 2}
                cy={size / 2}
                r={r}
                fill="none"
                strokeWidth={active === s.status ? stroke + 5 : stroke}
                strokeLinecap="butt"
                style={{
                  ...delay(i * 0.08),
                  "--c": `${c}px`,
                  stroke: toneColor(STATUS_META[s.status].tone),
                  strokeDasharray: `${s.len}px ${c - s.len}px`,
                  strokeDashoffset: `${-s.offset}px`,
                  cursor: onSelect ? "pointer" : "default",
                } as CSSProperties}
                onClick={() => onSelect?.(s.status)}
              >
                <title>{`${STATUS_META[s.status].label}: ${s.value}`}</title>
              </circle>
            ))}
          </g>
        </svg>
        <div className="donut-center">
          <strong><AnimatedNumber value={total} /></strong>
          <span>{centerLabel}</span>
        </div>
      </div>
      <ul className="donut-legend">
        {order.map((s) => {
          const v = counts[s] ?? 0;
          const pct = total ? Math.round((v / total) * 100) : 0;
          return (
            <li key={s}>
              <button
                type="button"
                className={`legend-item ${active === s ? "active" : ""}`}
                onClick={() => onSelect?.(s)}
                disabled={!onSelect}
              >
                <span className="legend-swatch" style={{ background: toneColor(STATUS_META[s].tone) }} />
                <span className="legend-label">{STATUS_META[s].short}</span>
                <span className="legend-value">{v}</span>
                <span className="legend-pct">{pct}%</span>
              </button>
            </li>
          );
        })}
      </ul>
    </div>
  );
}

/* --------------------------------------------------------------- activity */

const BUCKETS = [60, 5 * 60, 15 * 60, 60 * 60, 6 * 3600, 24 * 3600, 7 * 86400];
const N_BUCKETS = 12;

export function ActivityChart({ submissions, order }: { submissions: Submission[]; order: Status[] }) {
  const { buckets, size, max } = useMemo(() => {
    const now = Date.now();
    const times = submissions.map((s) => new Date(s.created_at).getTime()).filter((t) => !Number.isNaN(t));
    const earliest = times.length ? Math.min(...times) : now;
    const spanSec = Math.max((now - earliest) / 1000, 1);
    const size = BUCKETS.find((b) => spanSec / b <= N_BUCKETS - 1) ?? BUCKETS[BUCKETS.length - 1];
    const sizeMs = size * 1000;
    const end = Math.floor(now / sizeMs) * sizeMs + sizeMs;
    const start = end - N_BUCKETS * sizeMs;
    const buckets = Array.from({ length: N_BUCKETS }, (_, i) => ({
      start: start + i * sizeMs,
      counts: {} as Partial<Record<Status, number>>,
      total: 0,
    }));
    submissions.forEach((s) => {
      const t = new Date(s.created_at).getTime();
      const idx = Math.floor((t - start) / sizeMs);
      if (idx < 0 || idx >= N_BUCKETS) return;
      const b = buckets[idx];
      b.counts[s.status] = (b.counts[s.status] ?? 0) + 1;
      b.total += 1;
    });
    return { buckets, size, max: Math.max(1, ...buckets.map((b) => b.total)) };
  }, [submissions]);

  const label = (ms: number) => {
    const d = new Date(ms);
    if (size >= 86400) return d.toLocaleDateString(undefined, { day: "2-digit", month: "short" });
    return d.toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" });
  };
  const unit = size < 3600 ? `${size / 60} min` : size < 86400 ? `${size / 3600} h` : size === 86400 ? "day" : "week";

  return (
    <div className="activity">
      <div className="activity-plot">
        <div className="activity-grid" aria-hidden>
          {[0, 1, 2, 3].map((i) => <span key={i} />)}
        </div>
        {buckets.map((b, i) => (
          <div className="activity-col" key={b.start} title={`${label(b.start)} · ${b.total} submission(s)`}>
            <div className="activity-stack">
              {order.map((s) => {
                const v = b.counts[s] ?? 0;
                if (!v) return null;
                return (
                  <span
                    key={s}
                    className="activity-seg"
                    style={{ ...delay(i * 0.035), background: toneColor(STATUS_META[s].tone), height: `${(v / max) * 100}%` }}
                  />
                );
              })}
            </div>
            {b.total > 0 && <span className="activity-count">{b.total}</span>}
          </div>
        ))}
      </div>
      <div className="activity-axis">
        {buckets.map((b, i) => (
          <span key={b.start}>{i % 3 === 0 || i === N_BUCKETS - 1 ? label(b.start) : ""}</span>
        ))}
      </div>
      <div className="activity-foot muted small">Each bar = {unit}, coloured by current status</div>
    </div>
  );
}

/* ------------------------------------------------------------- issue bars */

export function IssueBars({ issues }: { issues: { code: string; title: string; count: number }[] }) {
  const max = issues[0]?.count || 1;
  return (
    <ul className="issue-bars">
      {issues.map((i, idx) => (
        <li key={i.code} className="a-slide" style={delay(idx * 0.05)}>
          <div className="issue-label">
            <span>{i.title}</span>
            <strong>{i.count}</strong>
          </div>
          <div className="issue-track">
            <div className="issue-fill" style={{ ...delay(0.1 + idx * 0.05), width: `${(i.count / max) * 100}%` }} />
          </div>
        </li>
      ))}
    </ul>
  );
}

/* ------------------------------------------------------------ progress ring */

export function ProgressRing({
  value,
  size = 64,
  stroke = 6,
  children,
  tone = "brand",
}: {
  value: number;
  size?: number;
  stroke?: number;
  children?: ReactNode;
  tone?: "brand" | "green" | "amber" | "violet" | "red" | "blue";
}) {
  const r = (size - stroke) / 2;
  return (
    <div className="ring" style={{ width: size, height: size }}>
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`}>
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" strokeWidth={stroke} style={{ stroke: "var(--surface-3)" }} />
        <circle
          className="ring-arc"
          cx={size / 2}
          cy={size / 2}
          r={r}
          fill="none"
          strokeWidth={stroke}
          strokeLinecap="round"
          transform={`rotate(-90 ${size / 2} ${size / 2})`}
          pathLength={1}
          style={{
            stroke: tone === "brand" ? "var(--brand)" : toneColor(tone),
            strokeDasharray: `${Math.max(0.0001, Math.min(1, value))} 1`,
          }}
        />
      </svg>
      {children && <div className="ring-center">{children}</div>}
    </div>
  );
}

/* -------------------------------------------------------------- risk gauge */

export function RiskGauge({ score }: { score: number | null | undefined }) {
  const value = Math.max(0, Math.min(100, score ?? 0));
  const tone = riskTone(value);
  const band = value >= 60 ? "High risk" : value >= 30 ? "Medium risk" : "Low risk";
  const w = 132;
  const r = 52;
  const cx = w / 2;
  const cy = 62;
  const arc = `M ${cx - r} ${cy} A ${r} ${r} 0 0 1 ${cx + r} ${cy}`;
  return (
    <div className="gauge" title={`Risk ${value}/100`}>
      <svg width={w} height={74} viewBox={`0 0 ${w} 74`}>
        <path d={arc} fill="none" strokeWidth={10} strokeLinecap="round" style={{ stroke: "var(--surface-3)" }} />
        <path
          className="gauge-arc"
          d={arc}
          fill="none"
          strokeWidth={10}
          strokeLinecap="round"
          pathLength={1}
          style={{ stroke: toneColor(tone), strokeDasharray: `${Math.max(0.02, value / 100)} 1` }}
        />
        {/* The needle is drawn pointing at 0 and rotated clockwise about the hub: 0 → 180deg maps to risk 0 → 100. */}
        <g className="gauge-needle" style={{ transform: `rotate(${(value / 100) * 180}deg)`, transformOrigin: `${cx}px ${cy}px` }}>
          <line x1={cx} y1={cy} x2={cx - (r - 14)} y2={cy} strokeWidth={3} strokeLinecap="round" style={{ stroke: "var(--ink)" }} />
        </g>
        <circle cx={cx} cy={cy} r={5} style={{ fill: "var(--ink)" }} />
      </svg>
      <div className="gauge-text">
        <strong className={`text-${tone}`}><AnimatedNumber value={value} /></strong>
        <span>{band}</span>
      </div>
    </div>
  );
}
