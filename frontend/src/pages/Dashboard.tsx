import { motion } from "framer-motion";
import { ArrowUpRight, Layers, Plus, RotateCcw, Search, Timer, TriangleAlert, Zap } from "lucide-react";
import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api } from "../api";
import { ActivityChart, IssueBars, ProgressRing, StatusDonut, toneColor } from "../components/charts";
import { HeroShield } from "../components/illustrations";
import { AnimatedNumber, Item, PageHeader, Rise, Stagger, delay } from "../components/motion";
import { EmptyState } from "../components/scenes";
import { RiskMeter, STATUS_META, STATUS_ORDER, StatusBadge, timeAgo, usePolling } from "../lib";
import type { Status } from "../types";

const FILTERS: { key: string; label: string }[] = [
  { key: "", label: "All" },
  { key: "PROCESSING", label: "Processing" },
  { key: "PENDING_VENDOR", label: "Awaiting vendor" },
  { key: "PENDING_REVIEW", label: "In review" },
  { key: "APPROVED", label: "Approved" },
  { key: "REJECTED", label: "Rejected" },
];

const KPI_STATUSES: Status[] = ["APPROVED", "PENDING_VENDOR", "PENDING_REVIEW", "REJECTED"];

function ConfirmDialog({ open, busy, onCancel, onConfirm }: { open: boolean; busy: boolean; onCancel: () => void; onConfirm: () => void }) {
  return (
    open ? (
        <div className="modal-backdrop a-fade" onClick={onCancel}>
          <div className="modal a-pop" role="dialog" aria-modal="true" aria-labelledby="reset-title" onClick={(e) => e.stopPropagation()}>
            <div className="modal-icon tone-red"><TriangleAlert size={22} /></div>
            <h3 id="reset-title">Reset demo data?</h3>
            <p className="muted">
              This deletes every submission, run, message and onboarded vendor, then restores the seeded vendor master (VEND-0001 to VEND-0003).
            </p>
            <div className="modal-actions">
              <button className="btn btn-ghost" onClick={onCancel} disabled={busy}>Cancel</button>
              <button className="btn btn-red" onClick={onConfirm} disabled={busy}>
                {busy ? "Resetting…" : "Yes, reset everything"}
              </button>
            </div>
          </div>
        </div>
    ) : null
  );
}

export default function Dashboard() {
  const navigate = useNavigate();
  const [filter, setFilter] = useState("");
  const [q, setQ] = useState("");
  const stats = usePolling(() => api.stats(), 3000);
  const list = usePolling(() => api.submissions(filter || undefined, q || undefined), 2500, [filter, q]);
  const all = usePolling(() => api.submissions(), 4000);
  const [confirming, setConfirming] = useState(false);
  const [resetting, setResetting] = useState(false);
  const [resetError, setResetError] = useState<string | null>(null);

  const s = stats.data;
  const count = (k: Status) => s?.by_status[k] ?? 0;
  const toggleFilter = (k: Status) => setFilter((f) => (f === k ? "" : k));

  const reset = async () => {
    setResetting(true);
    setResetError(null);
    try {
      await api.reset();
      stats.reload();
      list.reload();
      all.reload();
      setFilter("");
      setQ("");
      setConfirming(false);
    } catch (e) {
      setResetError((e as Error).message);
      setConfirming(false);
    } finally {
      setResetting(false);
    }
  };

  const rows = list.data ?? [];
  const hasAny = (s?.total ?? 0) > 0;

  return (
    <div className="page">
      <PageHeader
        eyebrow={<><Zap size={13} /> Live operations</>}
        title={<>Vendor onboarding <span className="grad-text">control room</span></>}
        subtitle="Every submission, its status and the reason behind it. Clean vendors are approved automatically; everything else is routed to the right owner."
        actions={
          <>
            <Link to="/new" className="btn btn-primary btn-lg"><Plus size={17} /> New submission</Link>
            <button className="btn btn-glass" onClick={() => setConfirming(true)} disabled={resetting}>
              <RotateCcw size={15} /> Reset demo data
            </button>
          </>
        }
        art={<HeroShield />}
      />

      {resetError && <div className="alert alert-red">{resetError}</div>}

      <Stagger className="kpis">
        <Item className="kpi kpi-total">
          <span className="kpi-icon"><Layers size={17} /></span>
          <span className="kpi-label">Total submissions</span>
          <strong className="kpi-value"><AnimatedNumber value={s?.total ?? null} /></strong>
          <small>{s?.runs_completed ?? 0} pipeline runs</small>
        </Item>
        {KPI_STATUSES.map((k) => {
          const Icon = STATUS_META[k].icon;
          return (
            <Item key={k}>
              <motion.button
                type="button"
                className={`kpi kpi-status kpi-${STATUS_META[k].tone} ${filter === k ? "kpi-active" : ""}`}
                onClick={() => toggleFilter(k)}
                whileHover={{ y: -3 }}
                whileTap={{ scale: 0.98 }}
                aria-pressed={filter === k}
              >
                <span className="kpi-icon"><Icon size={17} /></span>
                <span className="kpi-label">{STATUS_META[k].short}</span>
                <strong className="kpi-value"><AnimatedNumber value={s ? count(k) : null} /></strong>
                <small>{filter === k ? "Filtering · click to clear" : "Click to filter"}</small>
              </motion.button>
            </Item>
          );
        })}
        <Item className="kpi kpi-ring">
          <span className="kpi-icon kpi-ring-icon">
            <ProgressRing value={(s?.straight_through_rate ?? 0) / 100} size={28} stroke={4} />
          </span>
          <span className="kpi-label">Straight-through</span>
          <strong className="kpi-value">
            <AnimatedNumber value={s?.straight_through_rate != null ? Math.round(s.straight_through_rate) : null} suffix="%" />
          </strong>
          <small>decided with no human</small>
        </Item>
        <Item className="kpi kpi-time">
          <span className="kpi-icon tone-blue"><Timer size={17} /></span>
          <span className="kpi-label">Avg. run time</span>
          <strong className="kpi-value">
            <AnimatedNumber value={s?.avg_run_seconds ?? null} decimals={1} suffix="s" />
          </strong>
          <small>submission → decision</small>
        </Item>
      </Stagger>

      <Stagger className="chart-grid">
        <Item className="card chart-card">
          <div className="card-head">
            <div>
              <h3>Status mix</h3>
              <p className="muted small">Click a slice to filter the table</p>
            </div>
          </div>
          {hasAny ? (
            <StatusDonut counts={s?.by_status ?? {}} order={STATUS_ORDER} active={filter} onSelect={toggleFilter} />
          ) : (
            <div className="chart-empty"><EmptyState card={false} compact scene="submissions" title="No submissions yet">The donut fills in as runs finish.</EmptyState></div>
          )}
        </Item>
        <Item className="card chart-card">
          <div className="card-head">
            <div>
              <h3>Activity</h3>
              <p className="muted small">Submissions over time</p>
            </div>
            <div className="mini-legend">
              {STATUS_ORDER.filter((st) => st !== "PROCESSING").map((st) => (
                <span key={st}><i style={{ background: toneColor(STATUS_META[st].tone) }} />{STATUS_META[st].short}</span>
              ))}
            </div>
          </div>
          <ActivityChart submissions={all.data ?? []} order={STATUS_ORDER} />
        </Item>
        <Item className="card chart-card">
          <div className="card-head">
            <div>
              <h3>Where vendors trip up</h3>
              <p className="muted small">Most frequent issues across all runs</p>
            </div>
          </div>
          {(s?.top_issues ?? []).length === 0 ? (
            <div className="chart-empty"><EmptyState card={false} compact scene="all-clear" title="No issues recorded yet">Common vendor mistakes are ranked here.</EmptyState></div>
          ) : (
            <IssueBars issues={s!.top_issues} />
          )}
        </Item>
      </Stagger>

      <Rise as="section" className="card table-card" delay={0.25}>
        <div className="card-head">
          <div className="segmented" role="tablist" aria-label="Filter by status">
            {FILTERS.map((f) => (
              <button
                key={f.key}
                role="tab"
                aria-selected={filter === f.key}
                className={`segmented-item ${filter === f.key ? "active" : ""}`}
                onClick={() => setFilter(f.key)}
              >
                {filter === f.key && <motion.span layoutId="seg-active" className="segmented-bg" transition={{ type: "spring", stiffness: 500, damping: 38 }} />}
                <span>{f.label}</span>
              </button>
            ))}
          </div>
          <label className="search-box">
            <Search size={15} />
            <input placeholder="Search name, ID, PAN, GSTIN…" value={q} onChange={(e) => setQ(e.target.value)} />
          </label>
        </div>
        {list.error && <div className="alert alert-red">{list.error}</div>}
        {!list.data ? (
          !list.error && <EmptyState card={false} scene="loading" title="Loading submissions…" />
        ) : rows.length === 0 ? (
          <EmptyState
            card={false}
            scene={hasAny ? "no-match" : "submissions"}
            title={hasAny ? "No submissions match this view" : "No submissions yet"}
            action={hasAny ? (
              <button className="btn btn-ghost" onClick={() => { setFilter(""); setQ(""); }}>Clear filters</button>
            ) : (
              <Link to="/new" className="btn btn-primary">Run a demo scenario</Link>
            )}
          >
            {hasAny ? "Try a different filter or search term." : "Run a demo scenario to watch the pipeline in action."}
          </EmptyState>
        ) : (
          <div className="table-wrap">
            <table className="table table-click">
              <thead>
                <tr>
                  <th>Submission</th>
                  <th>Vendor</th>
                  <th>Status</th>
                  <th>Risk</th>
                  <th>Why</th>
                  <th className="center">Version · runs</th>
                  <th>Updated</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                  {rows.map((row, i) => (
                    <tr key={row.id} className="a-fade" style={delay(Math.min(i, 10) * 0.02)} onClick={() => navigate(`/submissions/${row.id}`)}>
                      <td><span className="id-pill mono">{row.id}</span></td>
                      <td>
                        <div className="vendor-cell">
                          <span className="avatar" data-tone={STATUS_META[row.status]?.tone}>{(row.legal_name || "?").slice(0, 1)}</span>
                          <div>
                            <div className="strong">{row.legal_name || <span className="muted">(no name)</span>}</div>
                            <div className="muted small mono">{row.gstin || row.pan || "—"}</div>
                          </div>
                        </div>
                      </td>
                      <td><StatusBadge status={row.status} /></td>
                      <td style={{ minWidth: 110 }}><RiskMeter score={row.risk_score} compact /></td>
                      <td className="why">{row.decision_reason ?? <span className="muted shimmer-text">Running checks…</span>}</td>
                      <td className="center small">v{row.current_version} · {row.run_count}</td>
                      <td className="muted small nowrap">{timeAgo(row.updated_at)}</td>
                      <td className="row-go"><ArrowUpRight size={16} /></td>
                    </tr>
                  ))}
              </tbody>
            </table>
          </div>
        )}
      </Rise>

      <ConfirmDialog open={confirming} busy={resetting} onCancel={() => !resetting && setConfirming(false)} onConfirm={reset} />
    </div>
  );
}
