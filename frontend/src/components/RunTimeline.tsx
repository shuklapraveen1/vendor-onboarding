import { motion } from "framer-motion";
import { ChevronDown, Lightbulb, MessageSquareWarning } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { RESOLUTION_META, StageIcon, StatusDot, Tag } from "../lib";
import type { Finding, Run, RunEvent, Severity, StageDef, StageResult, StageStatus, Status } from "../types";
import { ProgressRing } from "./charts";
import { delay } from "./motion";

export interface TimelineState {
  stages: Record<string, { status: StageStatus; counts?: Record<Severity, number>; duration_ms?: number }>;
  findings: Finding[];
  decision: { decision: Status; reason: string; risk_score: number; vendor_code?: string | null } | null;
  done: boolean;
  live: boolean;
}

function fromRun(run: Run, defs: StageDef[]): TimelineState {
  const stages: TimelineState["stages"] = {};
  defs.forEach((d) => (stages[d.key] = { status: "pending" }));
  (run.summary?.stages ?? []).forEach((s: StageResult) => {
    stages[s.stage] = { status: s.status, counts: s.counts, duration_ms: s.duration_ms };
  });
  return {
    stages,
    findings: run.findings ?? [],
    decision: run.decision
      ? { decision: run.decision, reason: run.decision_reason ?? "", risk_score: run.risk_score ?? 0 }
      : null,
    done: run.status !== "running",
    live: false,
  };
}

export function useRunTimeline(run: Run | null, defs: StageDef[], onComplete: () => void): TimelineState | null {
  const [state, setState] = useState<TimelineState | null>(null);

  useEffect(() => {
    if (!run || defs.length === 0) {
      setState(null);
      return;
    }
    if (run.status !== "running") {
      setState(fromRun(run, defs));
      return;
    }
    const initial: TimelineState = {
      stages: Object.fromEntries(defs.map((d) => [d.key, { status: "pending" as StageStatus }])),
      findings: [],
      decision: null,
      done: false,
      live: true,
    };
    setState(initial);
    const source = new EventSource(`/api/runs/${run.id}/events`);
    let finished = false;
    source.onmessage = (msg) => {
      const ev = JSON.parse(msg.data) as RunEvent;
      setState((prev) => {
        if (!prev) return prev;
        const next: TimelineState = { ...prev, stages: { ...prev.stages } };
        switch (ev.type) {
          case "stage_started":
            if (ev.stage) next.stages[ev.stage] = { status: "running" };
            break;
          case "check":
            next.findings = [...prev.findings, ev.payload as unknown as Finding];
            break;
          case "stage_completed": {
            const p = ev.payload as unknown as StageResult;
            next.stages[p.stage] = { status: p.status, counts: p.counts, duration_ms: p.duration_ms };
            break;
          }
          case "decision":
            next.decision = ev.payload as unknown as TimelineState["decision"];
            break;
          case "run_completed":
            next.done = true;
            next.live = false;
            break;
        }
        return next;
      });
      if (ev.type === "run_completed" && !finished) {
        finished = true;
        source.close();
        window.setTimeout(onComplete, 250);
      }
    };
    source.addEventListener("end", () => {
      source.close();
      if (!finished) {
        finished = true;
        onComplete();
      }
    });
    return () => source.close();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [run?.id, run?.status, defs.length]);

  return state;
}

function useElapsed(startedAt: string | undefined, finishedAt: string | null | undefined, live: boolean): number {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (!live) return;
    const id = window.setInterval(() => setNow(Date.now()), 100);
    return () => window.clearInterval(id);
  }, [live]);
  if (!startedAt) return 0;
  const start = new Date(startedAt).getTime();
  const end = live ? now : finishedAt ? new Date(finishedAt).getTime() : start;
  return Math.max(0, end - start);
}

const DONE = (s: StageStatus | undefined) => !!s && !["pending", "running"].includes(s);

function PipelineStrip({
  defs,
  state,
  onSelect,
}: {
  defs: StageDef[];
  state: TimelineState;
  onSelect: (key: string) => void;
}) {
  return (
    <div className="pipe" role="list" aria-label="Pipeline progress">
      {defs.map((d, i) => {
        const st = state.stages[d.key]?.status ?? "pending";
        const nextSt = defs[i + 1] ? state.stages[defs[i + 1].key]?.status : undefined;
        const filled = DONE(st);
        const flowing = filled && nextSt === "running";
        return (
          <div key={d.key} className="pipe-step" role="listitem">
            <motion.button
              type="button"
              className={`pipe-node pipe-${st}`}
              onClick={() => onSelect(d.key)}
              title={`${i + 1}. ${d.label}`}
              whileHover={{ scale: 1.12 }}
              whileTap={{ scale: 0.94 }}
              animate={st === "running" ? { scale: [1, 1.1, 1] } : { scale: 1 }}
              transition={st === "running" ? { duration: 1.2, repeat: Infinity } : { type: "spring", stiffness: 400, damping: 20 }}
            >
              {st === "running" && <span className="pipe-halo" />}
              <StageIcon stage={d.key} size={15} />
            </motion.button>
            <span className="pipe-label">{d.label.split(/[ &]/)[0]}</span>
            {i < defs.length - 1 && (
              <span className="pipe-link">
                <span className={`pipe-link-fill pipe-fill-${st}`} style={{ transform: `scaleX(${filled ? 1 : 0})` }} />
                {flowing && <span className="pipe-flow" />}
              </span>
            )}
          </div>
        );
      })}
    </div>
  );
}

function FindingRow({ f, index }: { f: Finding; index: number }) {
  const [open, setOpen] = useState(false);
  const hasEvidence = f.evidence && Object.keys(f.evidence).length > 0;
  return (
    <li className={`finding finding-${f.severity} a-slide`} style={delay(Math.min(index, 12) * 0.03)}>
      <StatusDot status={f.severity} size={20} />
      <div className="finding-body">
        <div className="finding-title">
          <span>{f.title}</span>
          {f.resolution && f.severity !== "pass" && f.severity !== "info" && (
            <Tag tone={RESOLUTION_META[f.resolution].tone}>{RESOLUTION_META[f.resolution].label}</Tag>
          )}
          <code className="finding-code">{f.code}</code>
        </div>
        {f.detail && <div className="finding-detail">{f.detail}</div>}
        {f.hint && <div className="finding-hint"><Lightbulb size={13} /> {f.hint}</div>}
        {f.vendor_action && f.severity === "fail" && (
          <div className="finding-action">
            <MessageSquareWarning size={14} />
            <span><strong>Vendor will be asked:</strong> {f.vendor_action}</span>
          </div>
        )}
        {hasEvidence && (
          <button type="button" className="link-btn" onClick={() => setOpen(!open)} aria-expanded={open}>
            {open ? "Hide evidence" : "Show evidence"}
          </button>
        )}
        {open && <pre className="evidence a-fade">{JSON.stringify(f.evidence, null, 2)}</pre>}
      </div>
    </li>
  );
}

export default function RunTimeline({
  defs,
  state,
  startedAt,
  finishedAt,
}: {
  defs: StageDef[];
  state: TimelineState;
  startedAt?: string;
  finishedAt?: string | null;
}) {
  const [expanded, setExpanded] = useState<Record<string, boolean>>({});
  const refs = useRef<Record<string, HTMLLIElement | null>>({});
  const byStage = useMemo(() => {
    const out: Record<string, Finding[]> = {};
    state.findings.forEach((f) => (out[f.stage] = [...(out[f.stage] ?? []), f]));
    return out;
  }, [state.findings]);
  const completed = defs.filter((d) => DONE(state.stages[d.key]?.status)).length;
  const runningIdx = defs.findIndex((d) => state.stages[d.key]?.status === "running");
  const totals = useMemo(() => {
    const t = { pass: 0, warn: 0, fail: 0, info: 0 };
    state.findings.forEach((f) => (t[f.severity] += 1));
    return t;
  }, [state.findings]);
  const elapsed = useElapsed(startedAt, finishedAt, state.live);
  const pct = defs.length ? completed / defs.length : 0;

  const focusStage = (key: string) => {
    setExpanded((e) => ({ ...e, [key]: true }));
    window.setTimeout(() => refs.current[key]?.scrollIntoView({ behavior: "smooth", block: "center" }), 60);
  };

  const statusLine = state.live
    ? runningIdx >= 0
      ? <>Stage {runningIdx + 1} of {defs.length} · <strong>{defs[runningIdx].label}</strong></>
      : <>Starting pipeline…</>
    : state.done
      ? <>All {defs.length} stages complete</>
      : <>Waiting to start</>;

  return (
    <div className={`timeline ${state.live ? "is-live" : ""}`}>
      <div className="run-hud">
        <ProgressRing value={pct} size={64} stroke={6}>
          <strong>{Math.round(pct * 100)}%</strong>
        </ProgressRing>
        <div className="run-hud-text">
          <div className="run-hud-status">
            {state.live && <span className="live-pill"><span className="live-dot" /> LIVE</span>}
            <span>{statusLine}</span>
          </div>
          <div className="run-hud-meta">
            <span className="mono">{(elapsed / 1000).toFixed(1)}s</span>
            <span className="count count-pass">{totals.pass} passed</span>
            {totals.warn > 0 && <span className="count count-warn">{totals.warn} warnings</span>}
            {totals.fail > 0 && <span className="count count-fail">{totals.fail} failed</span>}
            {totals.info > 0 && <span className="count count-info">{totals.info} info</span>}
          </div>
        </div>
      </div>

      <PipelineStrip defs={defs} state={state} onSelect={focusStage} />

      <ol className="stages">
        {defs.map((d, i) => {
          const s = state.stages[d.key] ?? { status: "pending" as StageStatus };
          const items = byStage[d.key] ?? [];
          const hasIssues = items.some((f) => f.severity === "fail" || f.severity === "warn");
          const isOpen = expanded[d.key] ?? (s.status === "running" || hasIssues || d.key === "decision");
          return (
            <li key={d.key} ref={(el) => (refs.current[d.key] = el)} className={`stage stage-${s.status}`}>
              <div className="stage-rail">
                <StatusDot status={s.status} />
                {i < defs.length - 1 && (
                  <span className="stage-line">
                    <span className="stage-line-fill" style={{ transform: `scaleY(${DONE(s.status) ? 1 : 0})` }} />
                  </span>
                )}
              </div>
              <div className="stage-card">
                <button
                  type="button"
                  className="stage-head"
                  onClick={() => setExpanded({ ...expanded, [d.key]: !isOpen })}
                  aria-expanded={isOpen}
                  disabled={items.length === 0}
                >
                  <span className={`stage-icon stage-icon-${s.status}`}><StageIcon stage={d.key} /></span>
                  <span className="stage-title">
                    <strong>{d.label}</strong>
                    <small>{d.description}</small>
                  </span>
                  <span className="stage-meta">
                    {s.counts && (
                      <>
                        {s.counts.pass > 0 && <span className="count count-pass">{s.counts.pass} ✓</span>}
                        {s.counts.warn > 0 && <span className="count count-warn">{s.counts.warn} !</span>}
                        {s.counts.fail > 0 && <span className="count count-fail">{s.counts.fail} ✕</span>}
                        {s.counts.info > 0 && <span className="count count-info">{s.counts.info} i</span>}
                      </>
                    )}
                    {s.status === "running" && <span className="running-text">running…</span>}
                    {s.duration_ms !== undefined && <span className="muted mono">{s.duration_ms} ms</span>}
                    {items.length > 0 && (
                      <span className={`chev ${isOpen ? "" : "chev-closed"}`}>
                        <ChevronDown size={16} />
                      </span>
                    )}
                  </span>
                </button>
                {isOpen && items.length > 0 && (
                  <div className="findings-wrap a-fade">
                    <ul className="findings">
                      {items.map((f, idx) => (
                        <FindingRow key={`${f.code}-${idx}`} f={f} index={idx} />
                      ))}
                    </ul>
                  </div>
                )}
              </div>
            </li>
          );
        })}
      </ol>
    </div>
  );
}
