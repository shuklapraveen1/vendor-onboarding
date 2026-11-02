import { motion } from "framer-motion";
import {
  Check,
  CircleCheck,
  ExternalLink,
  FileText,
  Hash,
  History,
  Lightbulb,
  ListChecks,
  Mail,
  RotateCw,
  ScrollText,
  ShieldAlert,
  ThumbsDown,
  ThumbsUp,
  Undo2,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api } from "../api";
import { RiskGauge } from "../components/charts";
import { delay } from "../components/motion";
import { EmptyState } from "../components/scenes";
import RunTimeline, { useRunTimeline } from "../components/RunTimeline";
import { RESOLUTION_META, STATUS_META, StatusBadge, Tag, duration, fmtTime, useAppConfig } from "../lib";
import type { DocumentRecord, Finding, Run, SubmissionDetail as Detail, VendorForm } from "../types";

const DOC_FIELD_MAP: Record<string, Record<string, string>> = {
  gst_certificate: { gstin: "tax.gstin", legal_name: "company.legal_name", trade_name: "company.trade_name" },
  pan_card: { pan: "tax.pan", name: "company.legal_name" },
  bank_proof: { account_number: "bank.account_number", ifsc: "bank.ifsc", account_holder_name: "bank.account_holder_name" },
  incorporation_certificate: { cin: "company.cin", company_name: "company.legal_name", date_of_incorporation: "company.date_of_incorporation" },
  msme_certificate: { udyam_number: "tax.udyam_number", enterprise_name: "company.legal_name" },
};

function getPath(form: VendorForm | undefined, path: string): string {
  if (!form) return "";
  const [section, key] = path.split(".");
  const v = (form as unknown as Record<string, Record<string, unknown>>)[section]?.[key];
  return v === undefined || v === null ? "" : String(v);
}

const squash = (s: string) => s.replace(/[^A-Za-z0-9]/g, "").toUpperCase();
const relativeUrl = (url: string) => url.replace(/^https?:\/\/[^/]+/, "");

function DecisionBanner({ run, detail, live }: { run: Run | null; detail: Detail; live: boolean }) {
  const sub = detail.submission;
  if (live || !run || run.status === "running") {
    return (
      <div className="decision decision-running a-rise">
        <div className="decision-main">
          <div className="decision-orb orb-blue">
            <span className="orb-ring orb-ring-spin" />
            <RotateCw size={24} />
          </div>
          <div>
            <h2>Running checks…</h2>
            <p className="muted">Each stage updates live as it executes. Nothing to do yet.</p>
          </div>
        </div>
      </div>
    );
  }
  const isLatest = detail.latest_run?.id === run.id;
  const status = isLatest ? sub.status : run.decision ?? "PENDING_REVIEW";
  const meta = STATUS_META[status];
  const Icon = meta.icon;
  const reason = isLatest ? sub.decision_reason : run.decision_reason;
  return (
    <div key={`${run.id}-${status}`} className={`decision decision-${meta.tone} a-pop`}>
      <div className="decision-main">
        <div className={`decision-orb orb-${meta.tone} orb-enter`}>
          <Icon size={28} strokeWidth={2.2} />
        </div>
        <div className="decision-text">
          <StatusBadge status={status} large />
          <h2>{reason}</h2>
          <p className="muted small">
            {isLatest && sub.decided_by?.startsWith("reviewer:")
              ? `Final decision by ${sub.decided_by.replace("reviewer:", "")}. System decision for this run: ${run.decision?.replace("_", " ").toLowerCase()}.`
              : `Decided by rules engine · run ${run.id} · version ${run.version} · ${duration(run.started_at, run.finished_at)}`}
          </p>
        </div>
      </div>
      <div className="decision-side">
        <RiskGauge score={run.risk_score} />
        {sub.vendor_code && isLatest && (
          <div className="vendor-code a-rise" style={delay(0.4)}>
            <Hash size={13} /> Vendor code <strong>{sub.vendor_code}</strong>
          </div>
        )}
      </div>
    </div>
  );
}

function ReviewPanel({ detail, onDone }: { detail: Detail; onDone: () => void }) {
  const [reviewer, setReviewer] = useState(() => localStorage.getItem("reviewer") ?? "");
  const [note, setNote] = useState("");
  const [vendorNote, setVendorNote] = useState("");
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const act = async (action: string) => {
    setBusy(action);
    setError(null);
    try {
      localStorage.setItem("reviewer", reviewer);
      await api.review(detail.submission.id, { action, reviewer, note, vendor_note: vendorNote || undefined });
      setNote("");
      setVendorNote("");
      onDone();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(null);
    }
  };
  const valid = reviewer.trim().length >= 2 && note.trim().length >= 10;
  const noteLen = note.trim().length;

  return (
    <div className="card review-panel a-rise">
      <div className="review-head">
        <span className="review-icon"><ShieldAlert size={18} /></span>
        <div>
          <h3>Reviewer decision</h3>
          <p className="muted small">The system flagged this case for a human. Every action is recorded in the audit trail with your note.</p>
        </div>
      </div>
      {detail.review.open_vendor_items > 0 && (
        <div className="alert alert-amber small">
          {detail.review.open_vendor_items} vendor-fixable issue(s) are open, so approval is blocked. Use <strong>Request info</strong> to send them to the vendor.
        </div>
      )}
      <label className="field">
        <span className="field-label">Your name<em>*</em></span>
        <input value={reviewer} onChange={(e) => setReviewer(e.target.value)} placeholder="e.g. Priya (Compliance)" />
      </label>
      <label className="field">
        <span className="field-label">
          Internal note (audit trail)<em>*</em>
          <span className={`char-count ${noteLen >= 10 ? "ok" : ""}`}>{noteLen >= 10 ? <Check size={12} /> : `${noteLen}/10`}</span>
        </span>
        <textarea rows={3} value={note} onChange={(e) => setNote(e.target.value)} placeholder="Why you're making this decision (min 10 characters)" />
      </label>
      <label className="field">
        <span className="field-label">Note to vendor (optional)</span>
        <textarea rows={2} value={vendorNote} onChange={(e) => setVendorNote(e.target.value)} placeholder="Added to the email the vendor receives" />
      </label>
      {error && <div className="alert alert-red small">{error}</div>}
      <div className="review-actions">
        <button className="btn btn-green" disabled={!valid || !detail.review.can_approve || !!busy} onClick={() => act("approve")}
          title={!detail.review.can_approve ? "Open vendor-fixable issues must be resolved first" : ""}>
          <ThumbsUp size={15} /> {busy === "approve" ? "Approving…" : "Approve"}
        </button>
        <button className="btn btn-amber" disabled={!valid || !!busy} onClick={() => act("request_info")}>
          <Undo2 size={15} /> {busy === "request_info" ? "Sending…" : "Request info"}
        </button>
        <button className="btn btn-red" disabled={!valid || !!busy} onClick={() => act("reject")}>
          <ThumbsDown size={15} /> {busy === "reject" ? "Rejecting…" : "Reject"}
        </button>
      </div>
    </div>
  );
}

function NextSteps({ detail, findings }: { detail: Detail; findings: Finding[] }) {
  const sub = detail.submission;
  const vendorItems = findings.filter((f) => f.resolution === "vendor" && f.severity === "fail" && f.vendor_action);
  const flags = findings.filter((f) => (f.resolution === "review" || f.resolution === "reject") && (f.severity === "fail" || f.severity === "warn"));
  const warns = findings.filter((f) => f.severity === "warn" && !f.resolution);
  return (
    <div className="next-steps">
      {sub.status === "PENDING_VENDOR" && (
        <>
          <h4>What we asked the vendor for</h4>
          <ol className="asks">
            {vendorItems.map((f, i) => (
              <li key={i} className="a-slide" style={delay(i * 0.06)}>
                <span className="ask-num">{i + 1}</span>
                <div>
                  {f.vendor_action}
                  {f.hint && <div className="finding-hint"><Lightbulb size={13} /> {f.hint}</div>}
                </div>
              </li>
            ))}
          </ol>
          <a className="btn btn-primary btn-sm" href={relativeUrl(detail.portal_url)} target="_blank" rel="noreferrer">
            Open vendor portal link <ExternalLink size={14} />
          </a>
        </>
      )}
      {flags.length > 0 && (
        <>
          <h4>{sub.status === "REJECTED" ? "Why it was rejected" : "Why a human needs to look"}</h4>
          <ul className="flags">
            {flags.map((f, i) => (
              <li key={i} className="a-rise" style={delay(i * 0.06)}>
                <Tag tone={RESOLUTION_META[f.resolution!].tone}>{RESOLUTION_META[f.resolution!].label}</Tag>
                <div>
                  <strong>{f.title}</strong>
                  <div className="small muted">{f.detail}</div>
                </div>
              </li>
            ))}
          </ul>
        </>
      )}
      {sub.status === "PENDING_REVIEW" && vendorItems.length > 0 && (
        <>
          <h4>Held vendor-fixable items</h4>
          <ul className="plain small">{vendorItems.map((f, i) => <li key={i}>{f.title}</li>)}</ul>
        </>
      )}
      {sub.status === "APPROVED" && (
        <div className="success-note">
          <CircleCheck size={20} />
          <p>Vendor created as <strong>{sub.vendor_code}</strong> in the vendor master. A welcome email with payment details was drafted.</p>
        </div>
      )}
      {warns.length > 0 && (
        <>
          <h4>Non-blocking warnings</h4>
          <ul className="plain small">{warns.map((f, i) => <li key={i}>{f.title} <span className="muted">(+{f.weight} risk)</span></li>)}</ul>
        </>
      )}
      {sub.status === "REJECTED" && flags.length === 0 && <p className="muted">{sub.decision_reason}</p>}
    </div>
  );
}

function DocumentsTab({ docs, form }: { docs: DocumentRecord[]; form?: VendorForm }) {
  const config = useAppConfig();
  if (docs.length === 0) {
    return (
      <EmptyState card={false} compact scene="documents" title="No documents uploaded">
        The vendor submitted the form without attachments. Required documents are requested in the follow-up email.
      </EmptyState>
    );
  }
  return (
    <div className="docs">
      {docs.map((d, i) => {
        const ex = d.extraction;
        const wrongType = ex && ex.classified_as !== d.slot;
        const mapping = DOC_FIELD_MAP[ex?.classified_as ?? ""] ?? {};
        return (
          <div className="doc-card a-rise" key={d.id} style={delay(i * 0.05)}>
            <div className="doc-card-head">
              <span className="doc-icon">PDF</span>
              <div className="doc-card-title">
                <strong>{config?.document_slots[d.slot] ?? d.slot}</strong>
                <div className="small muted">
                  <a href={`/api/documents/${d.id}/file`} target="_blank" rel="noreferrer">{d.filename}</a> · {(d.size_bytes / 1024).toFixed(0)} KB · sha256 {d.sha256.slice(0, 10)}…
                  {d.carried_over ? " · carried over from earlier version" : ""}
                </div>
              </div>
              {ex && (
                <div className="row gap wrap">
                  {!ex.readable ? <Tag tone="red">Unreadable</Tag> : wrongType ? (
                    <Tag tone="red">Actually: {config?.document_slots[ex.classified_as] ?? ex.classified_as}</Tag>
                  ) : <Tag tone="green">Recognised</Tag>}
                  <Tag tone="gray">{ex.engine}</Tag>
                </div>
              )}
            </div>
            {ex && ex.readable && Object.keys(ex.fields).length > 0 && (
              <div className="table-wrap">
                <table className="table table-compact">
                  <thead>
                    <tr><th>Field</th><th>On document</th><th>On form</th><th></th></tr>
                  </thead>
                  <tbody>
                    {Object.entries(ex.fields).filter(([k]) => k !== "subtype").map(([k, v]) => {
                      const formVal = mapping[k] ? getPath(form, mapping[k]) : "";
                      const cmp = mapping[k] && formVal ? (squash(formVal) === squash(v) ? "same" : "differs") : "";
                      return (
                        <tr key={k}>
                          <td className="muted">{k.replace(/_/g, " ")}{ex.field_sources[k] === "llm" && <Tag tone="violet">LLM</Tag>}</td>
                          <td className="mono small">{v}</td>
                          <td className="mono small">{formVal || <span className="muted">—</span>}</td>
                          <td>{cmp === "same" ? <span className="cmp cmp-same">=</span> : cmp === "differs" ? <span className="cmp cmp-diff" title="Text differs; see findings for the normalised comparison">≠</span> : null}</td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}
            {ex && ex.issues.length > 0 && <ul className="plain small text-amber">{ex.issues.map((iss, n) => <li key={n}>{iss}</li>)}</ul>}
          </div>
        );
      })}
    </div>
  );
}

function VersionsTab({ detail }: { detail: Detail }) {
  const versions = detail.versions;
  const diffs = useMemo(() => {
    return versions.map((v, idx) => {
      if (idx === 0) return [];
      const prev = versions[idx - 1].data as unknown as Record<string, Record<string, unknown>>;
      const cur = v.data as unknown as Record<string, Record<string, unknown>>;
      const out: { path: string; from: string; to: string }[] = [];
      Object.keys(cur).forEach((section) =>
        Object.keys(cur[section] ?? {}).forEach((k) => {
          const a = String(prev?.[section]?.[k] ?? "");
          const b = String(cur[section][k] ?? "");
          if (a !== b) out.push({ path: `${section}.${k}`, from: a, to: b });
        }),
      );
      return out;
    });
  }, [versions]);
  return (
    <div className="versions">
      {versions.slice().reverse().map((v) => {
        const idx = versions.indexOf(v);
        return (
          <div key={v.version} className="version">
            <span className="version-dot">v{v.version}</span>
            <div className="version-body">
              <div className="row between wrap gap">
                <strong>Version {v.version}</strong>
                <span className="muted small">{v.source.replace("_", " ")} · {fmtTime(v.created_at)}</span>
              </div>
              {idx > 0 && (
                diffs[idx].length === 0 ? <p className="muted small">No field changes (documents only).</p> : (
                  <table className="table table-compact">
                    <tbody>
                      {diffs[idx].map((d) => (
                        <tr key={d.path}>
                          <td className="muted">{d.path}</td>
                          <td className="mono small strike">{d.from || "∅"}</td>
                          <td className="mono small diff-new">{d.to || "∅"}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                )
              )}
              {idx === 0 && (
                <details>
                  <summary className="small">Show submitted data</summary>
                  <pre className="evidence">{JSON.stringify(v.data, null, 2)}</pre>
                </details>
              )}
            </div>
          </div>
        );
      })}
    </div>
  );
}

const TABS = [
  { key: "summary", label: "Summary", icon: ListChecks },
  { key: "documents", label: "Documents", icon: FileText },
  { key: "messages", label: "Messages", icon: Mail },
  { key: "versions", label: "Versions", icon: History },
  { key: "audit", label: "Audit trail", icon: ScrollText },
] as const;

export default function SubmissionDetail() {
  const { id = "" } = useParams();
  const config = useAppConfig();
  const [detail, setDetail] = useState<Detail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null);
  const [selectedRun, setSelectedRun] = useState<Run | null>(null);
  const [tab, setTab] = useState<string>("summary");
  const [rerunning, setRerunning] = useState(false);
  const [rerunError, setRerunError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const d = await api.submission(id);
      setDetail(d);
      setError(null);
      return d;
    } catch (e) {
      setError((e as Error).message);
      return null;
    }
  }, [id]);

  useEffect(() => {
    setSelectedRunId(null);
    load();
  }, [id, load]);

  useEffect(() => {
    if (!detail) return;
    const latest = detail.latest_run;
    const target = selectedRunId ?? latest?.id ?? null;
    if (!target) return setSelectedRun(null);
    if (latest && target === latest.id) setSelectedRun(latest);
    else api.run(target).then(setSelectedRun).catch(() => setSelectedRun(null));
  }, [detail, selectedRunId]);

  useEffect(() => {
    if (detail?.submission.status !== "PROCESSING" || detail.latest_run?.status === "running") return;
    const t = window.setTimeout(load, 1000);
    return () => window.clearTimeout(t);
  }, [detail, load]);

  const stages = config?.stages ?? [];
  const timeline = useRunTimeline(selectedRun, stages, load);

  if (error) {
    return (
      <div className="page">
        <EmptyState scene="not-found" title="Couldn't load this submission" action={<Link to="/" className="btn btn-primary">Back to dashboard</Link>}>
          {error}
        </EmptyState>
      </div>
    );
  }
  if (!detail || !timeline) {
    return (
      <div className="page">
        <div className="skeleton skeleton-banner" />
        <div className="detail-grid">
          <div className="skeleton skeleton-card" />
          <div className="skeleton skeleton-card" />
        </div>
      </div>
    );
  }

  const sub = detail.submission;
  const isLatest = !selectedRunId || selectedRunId === detail.latest_run?.id;
  const currentForm = detail.versions.find((v) => v.version === (selectedRun?.version ?? sub.current_version))?.data;
  const live = timeline.live;
  const vendorMsgs = detail.messages;
  const tabCount: Record<string, number | undefined> = {
    documents: detail.documents.length,
    messages: vendorMsgs.length,
    versions: detail.versions.length,
  };

  const rerun = async () => {
    setRerunning(true);
    setRerunError(null);
    try {
      await api.rerun(sub.id);
      setSelectedRunId(null);
      await load();
    } catch (e) {
      setRerunError((e as Error).message);
    } finally {
      setRerunning(false);
    }
  };

  return (
    <div className="page">
      <header className="detail-head">
        <div className="detail-head-main">
          <div className="crumbs"><Link to="/">Dashboard</Link> <span>/</span> <span className="mono">{sub.id}</span></div>
          <div className="detail-title">
            <span className="avatar avatar-lg" data-tone={STATUS_META[sub.status]?.tone}>{(sub.legal_name || "?").slice(0, 1)}</span>
            <h1>{sub.legal_name || "(unnamed vendor)"}</h1>
          </div>
          <div className="meta-chips">
            <span className="meta-chip mono">PAN {sub.pan || "—"}</span>
            <span className="meta-chip mono">GSTIN {sub.gstin || "—"}</span>
            <span className="meta-chip">Submitted {fmtTime(sub.created_at)}</span>
            {sub.scenario_id && <span className="meta-chip meta-chip-brand">scenario {sub.scenario_id}</span>}
          </div>
        </div>
        <div className="row gap wrap">
          {detail.runs.length > 1 && (
            <select className="run-select" value={selectedRunId ?? detail.latest_run?.id ?? ""} onChange={(e) => setSelectedRunId(e.target.value)} aria-label="Select run">
              {detail.runs.map((r, i) => (
                <option key={r.id} value={r.id}>
                  {i === 0 ? "Latest · " : ""}v{r.version} · {r.decision?.replace("_", " ").toLowerCase() ?? r.status} · {fmtTime(r.started_at)}
                </option>
              ))}
            </select>
          )}
          <button className="btn btn-ghost" onClick={rerun} disabled={rerunning || live || ["PROCESSING", "APPROVED"].includes(sub.status)}>
            <RotateCw size={15} className={rerunning ? "spin" : ""} /> Re-run
          </button>
        </div>
      </header>

      {rerunError && <div className="alert alert-red">{rerunError}</div>}
      <DecisionBanner run={selectedRun} detail={detail} live={live} />
      {!isLatest && (
        <div className="alert alert-blue small">
          Viewing an earlier run. <button className="link-btn" onClick={() => setSelectedRunId(null)}>Back to latest</button>
        </div>
      )}

      <div className="detail-grid">
        <section className="card run-card a-rise" style={delay(0.05)}>
          <div className="card-head">
            <div>
              <h3>Live run view</h3>
              <span className="muted small">
                {selectedRun ? `${selectedRun.id} · v${selectedRun.version}` : ""}
                {selectedRun?.engine?.llm?.enabled ? ` · AI assist: ${selectedRun.engine.llm.provider}` : " · rules + parsers"}
              </span>
            </div>
          </div>
          <RunTimeline defs={stages} state={timeline} startedAt={selectedRun?.started_at} finishedAt={selectedRun?.finished_at} />
        </section>

        <section className="side-col">
          {isLatest && sub.status === "PENDING_REVIEW" && !live && <ReviewPanel detail={detail} onDone={load} />}
          <div className="card tabs-card a-rise" style={delay(0.1)}>
            <div className="tabs" role="tablist">
              {TABS.map((t) => (
                <button key={t.key} role="tab" aria-selected={tab === t.key} className={`tab ${tab === t.key ? "tab-active" : ""}`} onClick={() => setTab(t.key)}>
                  <t.icon size={14} />
                  {t.label}
                  {tabCount[t.key] !== undefined && <span className="tab-count">{tabCount[t.key]}</span>}
                  {tab === t.key && <motion.span layoutId="tab-underline" className="tab-underline" transition={{ type: "spring", stiffness: 500, damping: 38 }} />}
                </button>
              ))}
            </div>
            <div key={tab} className="a-fade" role="tabpanel">
                {tab === "summary" && (live ? (
                  <div className="waiting"><span className="spinner" /> Waiting for the run to finish…</div>
                ) : <NextSteps detail={detail} findings={timeline.findings} />)}
                {tab === "documents" && <DocumentsTab docs={detail.documents} form={currentForm} />}
                {tab === "messages" && (
                  <div className="messages">
                    {vendorMsgs.length === 0 && (
                      <EmptyState card={false} compact scene="messages" title={live ? "Drafting messages…" : "No messages yet"}>
                        {live ? "The vendor email is drafted in the final stage of the run." : "Emails for this case will appear here once the run decides."}
                      </EmptyState>
                    )}
                    {vendorMsgs.map((m) => (
                      <details key={m.id} className={`message message-${m.audience}`} open={m.id === vendorMsgs[0]?.id}>
                        <summary>
                          <Tag tone={m.audience === "vendor" ? "blue" : "violet"}>{m.audience === "vendor" ? "To vendor" : "Internal"}</Tag>
                          <span className="strong">{m.subject}</span>
                          <span className="muted small">{fmtTime(m.created_at)}</span>
                        </summary>
                        <div className="small muted">To: {m.to_address} · drafted by {m.engine}</div>
                        <pre className="email">{m.body}</pre>
                        {m.action_url && m.audience === "vendor" && (
                          <a className="btn btn-sm btn-primary" href={relativeUrl(m.action_url)} target="_blank" rel="noreferrer">
                            Open link as vendor <ExternalLink size={13} />
                          </a>
                        )}
                      </details>
                    ))}
                  </div>
                )}
                {tab === "versions" && <VersionsTab detail={detail} />}
                {tab === "audit" && (
                  <ul className="audit">
                    {detail.audit.map((a, i) => (
                      <li key={a.id} className="a-slide" style={delay(Math.min(i, 15) * 0.03)}>
                        <span className="audit-dot" data-actor={a.actor.split(":")[0]} />
                        <div className="audit-body">
                          <div className="row gap wrap">
                            <span className={`actor actor-${a.actor.split(":")[0]}`}>{a.actor}</span>
                            <span className="strong">{a.action.replace(/_/g, " ")}</span>
                            <span className="muted small mono">{fmtTime(a.ts)}</span>
                          </div>
                          {Object.keys(a.details).length > 0 && (
                            <div className="muted small">
                              {Object.entries(a.details).filter(([, v]) => v !== null && v !== undefined && v !== "")
                                .map(([k, v]) => `${k}: ${typeof v === "object" ? JSON.stringify(v) : v}`).join(" · ")}
                            </div>
                          )}
                        </div>
                      </li>
                    ))}
                  </ul>
                )}
            </div>
          </div>
        </section>
      </div>
    </div>
  );
}
