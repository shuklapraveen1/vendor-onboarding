import { motion } from "framer-motion";

const float = (delay = 0, dist = 6) => ({
  animate: { y: [0, -dist * 0.5, 0] },
  transition: { duration: 6, repeat: Infinity, ease: "easeInOut" as const, delay },
});

function Paper({ x, y, w = 70, h = 88, rotate = 0, lines = 4, accent }: { x: number; y: number; w?: number; h?: number; rotate?: number; lines?: number; accent?: string }) {
  return (
    <g transform={`translate(${x} ${y}) rotate(${rotate})`}>
      <rect width={w} height={h} rx="9" style={{ fill: "var(--surface)", stroke: "var(--line)" }} strokeWidth="1.5" />
      <rect x="10" y="12" width={w * 0.45} height="7" rx="3.5" style={{ fill: accent ?? "var(--brand-soft-strong)" }} />
      {Array.from({ length: lines }, (_, i) => (
        <rect key={i} x="10" y={28 + i * 12} width={w - 20 - (i % 2) * 14} height="5" rx="2.5" style={{ fill: "var(--surface-3)" }} />
      ))}
    </g>
  );
}

export function HeroShield() {
  return (
    <svg viewBox="0 0 300 200" className="illus" role="img" aria-label="Verification illustration">
      <circle cx="160" cy="100" r="86" className="art-wash" />
      <motion.g {...float(0.4, 5)}>
        <Paper x={60} y={50} rotate={-12} />
      </motion.g>
      <motion.g {...float(1.2, 5)}>
        <Paper x={188} y={46} rotate={10} accent="color-mix(in srgb, var(--green) 35%, transparent)" />
      </motion.g>
      <motion.g {...float(0, 7)}>
        <path d="M160 34 L206 52 V96 C206 128 186 152 160 164 C134 152 114 128 114 96 V52 Z" className="art-ink" />
        <path d="M160 46 L196 60 V96 C196 121 181 141 160 151 C139 141 124 121 124 96 V60 Z" fill="none" style={{ stroke: "var(--on-brand)" }} strokeOpacity=".35" strokeWidth="1.5" />
        <motion.path d="M142 99 L155 112 L180 86" fill="none" style={{ stroke: "var(--on-brand)" }} strokeWidth="8" strokeLinecap="round" strokeLinejoin="round"
          initial={{ pathLength: 0 }} animate={{ pathLength: 1 }} transition={{ duration: 0.9, delay: 0.5, ease: "easeOut" }} />
      </motion.g>
      <motion.g {...float(0.8, 4)}>
        <rect x="40" y="140" width="64" height="24" rx="12" style={{ fill: "var(--surface)", stroke: "var(--line)" }} />
        <circle cx="54" cy="152" r="6" style={{ fill: "var(--green)" }} />
        <path d="M51 152 l2 2 l4 -4" style={{ stroke: "var(--on-brand)" }} strokeWidth="1.8" fill="none" strokeLinecap="round" />
        <text x="66" y="156" fontSize="10.5" fontWeight="700" style={{ fill: "var(--ink-2)" }}>GSTIN</text>
      </motion.g>
      <motion.g {...float(1.6, 4)}>
        <rect x="214" y="146" width="62" height="24" rx="12" style={{ fill: "var(--surface)", stroke: "var(--line)" }} />
        <circle cx="228" cy="158" r="6" style={{ fill: "var(--violet)" }} />
        <path d="M225 158 l2 2 l4 -4" style={{ stroke: "var(--on-brand)" }} strokeWidth="1.8" fill="none" strokeLinecap="round" />
        <text x="240" y="162" fontSize="10.5" fontWeight="700" style={{ fill: "var(--ink-2)" }}>BANK</text>
      </motion.g>
    </svg>
  );
}

export function FormIllustration() {
  return (
    <svg viewBox="0 0 300 200" className="illus" role="img" aria-label="Submission form illustration">
      <circle cx="150" cy="104" r="84" className="art-wash" />
      <g>
        <rect x="88" y="34" width="124" height="148" rx="14" style={{ fill: "var(--surface)", stroke: "var(--line)" }} strokeWidth="1.5" />
        <rect x="88" y="34" width="124" height="30" rx="14" className="art-ink" />
        <rect x="88" y="50" width="124" height="14" className="art-ink" />
        <circle cx="106" cy="49" r="6" style={{ fill: "var(--on-brand)" }} fillOpacity=".85" />
        <rect x="118" y="45" width="56" height="7" rx="3.5" style={{ fill: "var(--on-brand)" }} fillOpacity=".7" />
        {[78, 104, 130].map((y, i) => (
          <g key={y}>
            <rect x="102" y={y} width="40" height="5" rx="2.5" style={{ fill: "var(--surface-3)" }} />
            <motion.rect x="102" y={y + 9} height="12" rx="6" style={{ fill: "var(--brand-soft-strong)" }}
              initial={{ width: 0 }} animate={{ width: 96 }} transition={{ delay: 0.3 + i * 0.25, duration: 0.6 }} />
          </g>
        ))}
        <rect x="102" y="158" width="96" height="14" rx="7" className="art-ink" />
      </g>
      <motion.g {...float(0.3, 6)}>
        <rect x="214" y="70" width="48" height="58" rx="8" style={{ fill: "var(--surface)", stroke: "var(--line)" }} strokeWidth="1.5" />
        <rect x="222" y="80" width="22" height="12" rx="3" style={{ fill: "var(--red)" }} />
        <text x="225" y="89.5" fontSize="8" fontWeight="800" style={{ fill: "var(--on-brand)" }}>PDF</text>
        <rect x="222" y="100" width="32" height="4" rx="2" style={{ fill: "var(--surface-3)" }} />
        <rect x="222" y="110" width="24" height="4" rx="2" style={{ fill: "var(--surface-3)" }} />
      </motion.g>
      <motion.g {...float(1.1, 6)}>
        <circle cx="62" cy="80" r="22" style={{ fill: "var(--surface)", stroke: "var(--line)" }} strokeWidth="1.5" />
        <path d="M62 90 V70 M54 77 L62 69 L70 77" fill="none" style={{ stroke: "var(--brand)" }} strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" />
      </motion.g>
    </svg>
  );
}

export function ReviewIllustration() {
  return (
    <svg viewBox="0 0 300 200" className="illus" role="img" aria-label="Review illustration">
      <circle cx="150" cy="100" r="84" className="art-wash" />
      <motion.g {...float(0.5, 4)}>
        <Paper x={84} y={44} w={98} h={118} lines={6} />
      </motion.g>
      <motion.g animate={{ x: [0, 10, 0], y: [0, 6, 0] }} transition={{ duration: 7, repeat: Infinity, ease: "easeInOut" }}>
        <circle cx="168" cy="100" r="34" style={{ fill: "var(--surface)" }} className="art-stroke" strokeWidth="9" />
        <path d="M192 124 L222 154" className="art-stroke" strokeWidth="13" strokeLinecap="round" />
        <path d="M154 100 l10 10 l18 -20" fill="none" style={{ stroke: "var(--green)" }} strokeWidth="6" strokeLinecap="round" strokeLinejoin="round" />
      </motion.g>
    </svg>
  );
}

export function MailIllustration() {
  return (
    <svg viewBox="0 0 300 200" className="illus" role="img" aria-label="Outbox illustration">
      <circle cx="150" cy="104" r="84" className="art-wash" />
      <motion.path d="M36 150 C 90 120, 120 170, 176 118" fill="none" style={{ stroke: "var(--brand-soft-strong)" }} strokeWidth="2.5" strokeDasharray="5 7"
        animate={{ strokeDashoffset: [0, -48] }} transition={{ duration: 2.4, repeat: Infinity, ease: "linear" }} />
      <motion.g {...float(0, 7)}>
        <rect x="104" y="58" width="132" height="90" rx="12" className="art-ink" />
        <path d="M108 64 L170 108 L232 64" fill="none" style={{ stroke: "var(--on-brand)" }} strokeOpacity=".85" strokeWidth="5" strokeLinejoin="round" strokeLinecap="round" />
        <path d="M108 144 L152 106 M232 144 L188 106" style={{ stroke: "var(--on-brand)" }} strokeOpacity=".35" strokeWidth="3" strokeLinecap="round" />
      </motion.g>
      <motion.g {...float(1.2, 5)}>
        <circle cx="236" cy="56" r="16" style={{ fill: "var(--green)" }} />
        <path d="M229 56 l5 5 l9 -10" fill="none" style={{ stroke: "var(--on-brand)" }} strokeWidth="3.5" strokeLinecap="round" strokeLinejoin="round" />
      </motion.g>
    </svg>
  );
}

export function DatabaseIllustration() {
  const disk = (y: number, delay: number) => (
    <motion.g {...float(delay, 3)}>
      <path d={`M100 ${y} v26 c0 10 22 18 50 18 s50 -8 50 -18 v-26`} style={{ fill: "var(--surface)", stroke: "var(--line)" }} strokeWidth="1.5" />
      <ellipse cx="150" cy={y} rx="50" ry="17" className="art-ink" />
      <circle cx="182" cy={y + 30} r="3.5" style={{ fill: "var(--green)" }} />
      <rect x="112" y={y + 27} width="36" height="5" rx="2.5" style={{ fill: "var(--surface-3)" }} />
    </motion.g>
  );
  return (
    <svg viewBox="0 0 300 200" className="illus" role="img" aria-label="Vendor master illustration">
      <circle cx="150" cy="104" r="84" className="art-wash" />
      <g>
        {disk(128, 0.8)}
        {disk(88, 0.4)}
        {disk(48, 0)}
      </g>
      <motion.g {...float(1, 6)}>
        <rect x="214" y="60" width="58" height="24" rx="12" style={{ fill: "var(--surface)", stroke: "var(--line)" }} />
        <text x="226" y="76" fontSize="10.5" fontWeight="800" style={{ fill: "var(--brand)" }}>VEND</text>
      </motion.g>
    </svg>
  );
}

export function PipelineIllustration() {
  const nodes = [
    { x: 46, y: 120 },
    { x: 104, y: 70 },
    { x: 162, y: 118 },
    { x: 220, y: 66 },
    { x: 266, y: 112 },
  ];
  const d = nodes.map((n, i) => `${i === 0 ? "M" : "L"} ${n.x} ${n.y}`).join(" ");
  return (
    <svg viewBox="0 0 300 200" className="illus" role="img" aria-label="Process pipeline illustration">
      <circle cx="156" cy="100" r="84" className="art-wash" />
      <path d={d} fill="none" style={{ stroke: "var(--line)" }} strokeWidth="6" strokeLinecap="round" strokeLinejoin="round" />
      <motion.path d={d} fill="none" className="art-stroke" strokeWidth="6" strokeLinecap="round" strokeLinejoin="round"
        initial={{ pathLength: 0 }} animate={{ pathLength: [0, 1, 1] }} transition={{ duration: 3.2, repeat: Infinity, times: [0, 0.7, 1], ease: "easeInOut" }} />
      {nodes.map((n, i) => (
        <motion.g key={i} initial={{ scale: 0 }} animate={{ scale: 1 }} transition={{ delay: 0.15 * i, type: "spring", stiffness: 300 }}>
          <circle cx={n.x} cy={n.y} r="17" style={{ fill: "var(--surface)" }} className="art-stroke" strokeWidth="4" />
          <path d={`M${n.x - 6} ${n.y} l4 4 l8 -8`} fill="none" style={{ stroke: "var(--brand)" }} strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" />
        </motion.g>
      ))}
      <motion.g {...float(0.5, 5)}>
        <rect x="118" y="150" width="88" height="26" rx="13" className="art-ink" />
        <text x="134" y="167" fontSize="11" fontWeight="800" style={{ fill: "var(--on-brand)" }}>11 STAGES</text>
      </motion.g>
    </svg>
  );
}

export function PortalIllustration() {
  return (
    <svg viewBox="0 0 300 200" className="illus" role="img" aria-label="Supplier portal illustration">
      <circle cx="150" cy="104" r="84" className="art-wash" />
      <g>
        <rect x="70" y="72" width="78" height="96" rx="8" className="art-ink" />
        {[0, 1, 2].map((r) => [0, 1].map((c) => (
          <rect key={`${r}${c}`} x={84 + c * 28} y={86 + r * 22} width="18" height="12" rx="3" style={{ fill: "var(--on-brand)" }} fillOpacity=".55" />
        )))}
        <rect x="98" y="148" width="22" height="20" rx="3" style={{ fill: "var(--on-brand)" }} fillOpacity=".8" />
      </g>
      <motion.g {...float(0.4, 6)}>
        <rect x="160" y="54" width="86" height="104" rx="10" style={{ fill: "var(--surface)", stroke: "var(--line)" }} strokeWidth="1.5" />
        {[0, 1, 2, 3].map((i) => (
          <g key={i}>
            <circle cx="176" cy={76 + i * 22} r="6" style={{ fill: "var(--surface-3)" }} />
            <motion.circle cx="176" cy={76 + i * 22} r="6" style={{ fill: i < 3 ? "var(--green)" : "var(--amber)" }}
              initial={{ opacity: 0, scale: 0.3 }} animate={{ opacity: 1, scale: 1 }}
              transition={{ delay: 0.4 + i * 0.3, type: "spring", stiffness: 400, damping: 18 }} />
            <rect x="188" y={73 + i * 22} width={i === 3 ? 34 : 46} height="6" rx="3" style={{ fill: "var(--surface-3)" }} />
          </g>
        ))}
      </motion.g>
    </svg>
  );
}

export function UnpluggedIllustration() {
  return (
    <svg viewBox="0 0 240 150" className="illus" role="img" aria-label="Disconnected">
      <circle cx="120" cy="75" r="60" className="art-wash" />
      <motion.g animate={{ x: [-3, 0, -3] }} transition={{ duration: 2.4, repeat: Infinity }}>
        <path d="M20 75 H78" style={{ stroke: "var(--ink-2)" }} strokeWidth="5" strokeLinecap="round" />
        <rect x="78" y="58" width="30" height="34" rx="7" className="art-ink" />
        <path d="M108 66 h12 M108 84 h12" style={{ stroke: "var(--ink-2)" }} strokeWidth="5" strokeLinecap="round" />
      </motion.g>
      <motion.g animate={{ x: [3, 0, 3] }} transition={{ duration: 2.4, repeat: Infinity }}>
        <rect x="140" y="56" width="32" height="38" rx="7" style={{ fill: "var(--surface)", stroke: "var(--line)" }} strokeWidth="2" />
        <path d="M172 75 H220" style={{ stroke: "var(--ink-2)" }} strokeWidth="5" strokeLinecap="round" />
      </motion.g>
      <motion.path d="M124 40 l4 10 M134 36 l-1 11 M116 46 l8 6" style={{ stroke: "var(--amber)" }} strokeWidth="3" strokeLinecap="round"
        animate={{ opacity: [0, 1, 0] }} transition={{ duration: 1.4, repeat: Infinity }} />
    </svg>
  );
}
