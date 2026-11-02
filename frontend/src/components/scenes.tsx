import type { CSSProperties, ReactNode } from "react";

/*
 * Looping "GIF-style" scenes for empty and loading states. They are SVG animated with CSS
 * keyframes (classes `sc-*` in styles.css): crisp at any size, theme-aware through CSS variables,
 * time-based so they keep moving when the browser throttles frames, and paused automatically
 * by the reduced-motion media query.
 */

export type SceneKind =
  | "submissions" // dashboard, nothing submitted yet
  | "no-match" // a filter or search returned nothing
  | "all-clear" // review queue empty, no issues recorded
  | "inbox" // outbox empty
  | "messages" // a case with no vendor messages yet
  | "documents" // a case with no documents
  | "vendors" // vendor master empty
  | "loading" // waiting for the first response
  | "not-found"; // unknown route or link

const d = (seconds: number): CSSProperties => ({ animationDelay: `${seconds}s` });

const surface = { fill: "var(--surface)", stroke: "var(--line)" } as const;
const line = { fill: "var(--surface-3)" } as const;

function Frame({ label, children }: { label: string; children: ReactNode }) {
  return (
    <svg viewBox="0 0 240 160" className="scene" role="img" aria-label={label}>
      <ellipse cx="120" cy="146" rx="70" ry="7" className="sc-shadow" style={line} />
      <circle cx="120" cy="76" r="64" className="art-wash" />
      {children}
    </svg>
  );
}

function Submissions() {
  return (
    <Frame label="An empty tray waiting for submissions">
      {[0, 1, 2].map((i) => (
        <g key={i} className="sc-drop" style={d(i * 0.9)}>
          <rect x={102 + i * 6} y="20" width="36" height="44" rx="6" style={surface} strokeWidth="1.5" />
          <rect x={108 + i * 6} y="28" width="18" height="5" rx="2.5" className="art-ink" />
          <rect x={108 + i * 6} y="38" width="24" height="4" rx="2" style={line} />
          <rect x={108 + i * 6} y="46" width="20" height="4" rx="2" style={line} />
        </g>
      ))}
      <path d="M66 86 H174 L162 128 H78 Z" className="art-ink" />
      <path d="M66 86 L80 70 H160 L174 86" fill="none" className="art-stroke" strokeWidth="5" strokeLinejoin="round" />
      <path d="M100 104 H140" style={{ stroke: "var(--on-brand)" }} strokeOpacity=".6" strokeWidth="5" strokeLinecap="round" />
    </Frame>
  );
}

function NoMatch() {
  return (
    <Frame label="A magnifier searching rows and finding nothing">
      <rect x="62" y="34" width="116" height="96" rx="12" style={surface} strokeWidth="1.5" />
      {[0, 1, 2, 3].map((i) => (
        <g key={i}>
          <circle cx="78" cy={54 + i * 21} r="5" style={line} />
          <rect x="90" y={51 + i * 21} width={i % 2 ? 56 : 72} height="6" rx="3" style={line} />
        </g>
      ))}
      <g className="sc-sweep">
        <circle cx="104" cy="74" r="22" style={{ fill: "var(--surface)" }} fillOpacity="0.55" className="art-stroke" strokeWidth="7" />
        <path d="M120 90 L140 110" className="art-stroke" strokeWidth="10" strokeLinecap="round" />
        <path d="M96 70 q8 -8 16 0" fill="none" style={{ stroke: "var(--muted)" }} strokeWidth="3" strokeLinecap="round" className="sc-blink" />
      </g>
    </Frame>
  );
}

function AllClear() {
  return (
    <Frame label="A shield with a check mark: all clear">
      {[0, 1, 2].map((i) => (
        <circle key={i} cx="120" cy="76" r="40" fill="none" style={{ ...d(i * 0.8), stroke: "var(--brand)" }} strokeWidth="2" className="sc-ripple" />
      ))}
      <g className="sc-bob">
        <path d="M120 28 L156 42 V76 C156 101 140 119 120 128 C100 119 84 101 84 76 V42 Z" className="art-ink" />
        <path d="M104 76 L116 88 L138 64" fill="none" style={{ stroke: "var(--on-brand)" }} strokeWidth="8" strokeLinecap="round" strokeLinejoin="round" pathLength={1} className="sc-draw" />
      </g>
    </Frame>
  );
}

function Inbox() {
  return (
    <Frame label="An envelope flying into an empty outbox">
      <path d="M30 120 C 70 90, 100 130, 150 84" fill="none" style={{ stroke: "var(--brand-soft-strong)" }} strokeWidth="2.5" strokeDasharray="5 7" className="sc-dash" />
      <rect x="128" y="88" width="80" height="44" rx="8" style={surface} strokeWidth="1.5" />
      <path d="M128 100 H150 l6 10 h24 l6 -10 H208" fill="none" style={{ stroke: "var(--line-2)" }} strokeWidth="2" />
      <g className="sc-fly">
        <rect x="60" y="40" width="64" height="44" rx="8" className="art-ink" />
        <path d="M63 44 L92 66 L121 44" fill="none" style={{ stroke: "var(--on-brand)" }} strokeOpacity=".85" strokeWidth="4" strokeLinejoin="round" strokeLinecap="round" />
      </g>
    </Frame>
  );
}

function Messages() {
  return (
    <Frame label="Chat bubbles waiting for a message">
      <g className="sc-bob">
        <rect x="58" y="36" width="96" height="46" rx="16" className="art-ink" />
        <path d="M78 82 l-6 14 l18 -14" className="art-ink" />
        {[0, 1, 2].map((i) => (
          <circle key={i} cx={88 + i * 18} cy="59" r="5.5" className="sc-typing" style={{ ...d(i * 0.18), fill: "var(--on-brand)" }} />
        ))}
      </g>
      <g className="sc-bob" style={d(0.6)}>
        <rect x="112" y="90" width="76" height="36" rx="14" style={surface} strokeWidth="1.5" />
        <rect x="126" y="102" width="46" height="5" rx="2.5" style={line} />
        <rect x="126" y="112" width="30" height="5" rx="2.5" style={line} />
      </g>
    </Frame>
  );
}

function Documents() {
  return (
    <Frame label="A document with an upload arrow">
      <rect x="92" y="40" width="64" height="84" rx="9" style={surface} strokeWidth="1.5" transform="rotate(8 124 82)" />
      <g className="sc-bob">
        <rect x="80" y="32" width="64" height="84" rx="9" style={surface} strokeWidth="1.5" />
        <rect x="90" y="44" width="24" height="12" rx="3" style={{ fill: "var(--red)" }} />
        <text x="93" y="53.5" fontSize="8" fontWeight="800" style={{ fill: "var(--on-brand)" }}>PDF</text>
        {[0, 1, 2].map((i) => <rect key={i} x="90" y={66 + i * 11} width={i === 2 ? 28 : 44} height="5" rx="2.5" style={line} />)}
      </g>
      <g className="sc-hop">
        <circle cx="166" cy="104" r="18" className="art-ink" />
        <path d="M166 113 V96 M159 102 L166 95 L173 102" fill="none" style={{ stroke: "var(--on-brand)" }} strokeWidth="3.5" strokeLinecap="round" strokeLinejoin="round" />
      </g>
    </Frame>
  );
}

function Vendors() {
  return (
    <Frame label="A database waiting for its first vendor">
      {[98, 70, 42].map((y, i) => (
        <g key={y} className="sc-bob" style={d(i * 0.25)}>
          <path d={`M84 ${y} v20 c0 8 16 13 36 13 s36 -5 36 -13 v-20`} style={surface} strokeWidth="1.5" />
          <ellipse cx="120" cy={y} rx="36" ry="12" className="art-ink" />
          <circle cx="144" cy={y + 22} r="3" style={{ fill: "var(--green)" }} className="sc-blink" />
        </g>
      ))}
      <g className="sc-pulse">
        <circle cx="176" cy="46" r="15" style={{ fill: "var(--green)" }} />
        <path d="M176 39 V53 M169 46 H183" style={{ stroke: "var(--on-brand)" }} strokeWidth="3.5" strokeLinecap="round" />
      </g>
    </Frame>
  );
}

function Loading() {
  return (
    <Frame label="Loading">
      <rect x="84" y="26" width="72" height="96" rx="10" style={surface} strokeWidth="1.5" />
      <rect x="96" y="40" width="30" height="8" rx="4" className="art-ink" />
      {[0, 1, 2, 3, 4].map((i) => <rect key={i} x="96" y={58 + i * 11} width={i % 2 ? 36 : 48} height="5" rx="2.5" style={line} />)}
      <rect x="78" y="30" width="84" height="4" rx="2" className="art-ink sc-scan" />
    </Frame>
  );
}

function NotFound() {
  return (
    <Frame label="A compass looking for a page that does not exist">
      <g className="sc-bob">
        <circle cx="120" cy="76" r="40" style={surface} strokeWidth="2" />
        <circle cx="120" cy="76" r="32" fill="none" className="art-stroke" strokeWidth="4" strokeDasharray="4 6" />
        <g className="sc-wobble">
          <path d="M120 50 L128 76 L120 102 L112 76 Z" className="art-ink" />
          <circle cx="120" cy="76" r="4" style={{ fill: "var(--on-brand)" }} />
        </g>
      </g>
    </Frame>
  );
}

const SCENES: Record<SceneKind, () => JSX.Element> = {
  submissions: Submissions,
  "no-match": NoMatch,
  "all-clear": AllClear,
  inbox: Inbox,
  messages: Messages,
  documents: Documents,
  vendors: Vendors,
  loading: Loading,
  "not-found": NotFound,
};

export function Scene({ kind }: { kind: SceneKind }) {
  const Comp = SCENES[kind];
  return <Comp />;
}

/** A card-style empty state: animated scene, title, explanation and an optional action. */
export function EmptyState({
  scene,
  title,
  children,
  action,
  compact = false,
  card = true,
}: {
  scene: SceneKind;
  title?: ReactNode;
  children?: ReactNode;
  action?: ReactNode;
  compact?: boolean;
  card?: boolean;
}) {
  return (
    <div className={`empty-state a-pop ${card ? "card" : ""} ${compact ? "empty-compact" : ""}`} role={scene === "loading" ? "status" : undefined}>
      <Scene kind={scene} />
      {title && (compact ? <strong className="empty-title">{title}</strong> : <h3>{title}</h3>)}
      {children && <p className="muted">{children}</p>}
      {action}
    </div>
  );
}
