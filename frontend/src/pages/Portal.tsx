import { motion } from "framer-motion";
import { Check, Lightbulb, LoaderCircle, Lock, Send, Wand2 } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { useParams } from "react-router-dom";
import { api, loadScenarioFiles } from "../api";
import { LogoMark, ThemeToggle } from "../components/brand";
import DocumentSlots from "../components/DocumentSlots";
import { PortalIllustration } from "../components/illustrations";
import { delay } from "../components/motion";
import { EmptyState } from "../components/scenes";
import VendorFormFields from "../components/VendorFormFields";
import { STATUS_META, normalizeForm, requiredDocSlots, useAppConfig } from "../lib";
import type { PortalView, Status, VendorForm } from "../types";

type StepState = "done" | "current" | "todo" | "error";

function steps(status: Status, waiting: boolean): { label: string; state: StepState }[] {
  const s = waiting ? "PROCESSING" : status;
  const map: Record<Status, StepState[]> = {
    PROCESSING: ["done", "current", "todo", "todo"],
    PENDING_VENDOR: ["done", "done", "current", "todo"],
    PENDING_REVIEW: ["done", "done", "current", "todo"],
    APPROVED: ["done", "done", "done", "done"],
    REJECTED: ["done", "done", "done", "error"],
  };
  const third = s === "PENDING_REVIEW" ? "Under review" : s === "PENDING_VENDOR" ? "Your updates" : "Follow-up";
  const labels = ["Submitted", "Checks", third, s === "REJECTED" ? "Not approved" : "Approved"];
  return labels.map((label, i) => ({ label, state: map[s][i] }));
}

function Stepper({ status, waiting }: { status: Status; waiting: boolean }) {
  const items = steps(status, waiting);
  return (
    <ol className="stepper">
      {items.map((it, i) => (
        <li key={it.label} className={`step step-${it.state}`}>
          <span className="step-dot a-pop" style={delay(i * 0.1)}>
            {it.state === "done" ? <Check size={14} strokeWidth={3} /> : it.state === "current" ? <span className="step-pulse" /> : i + 1}
          </span>
          <span className="step-label">{it.label}</span>
          {i < items.length - 1 && (
            <span className="step-bar">
              <span
                className={`step-bar-fill ${it.state === "done" ? "is-filled" : ""}`}
                style={{ transitionDelay: `${0.1 + i * 0.12}s`, animationDelay: `${0.2 + i * 0.12}s` }}
              />
            </span>
          )}
        </li>
      ))}
    </ol>
  );
}

export default function Portal() {
  const { token = "" } = useParams();
  const config = useAppConfig();
  const [view, setView] = useState<PortalView | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [form, setForm] = useState<VendorForm | null>(null);
  const [files, setFiles] = useState<Record<string, File | null>>({});
  const [submitting, setSubmitting] = useState(false);
  const [waiting, setWaiting] = useState(false);
  const [hasFix, setHasFix] = useState(false);
  const [filling, setFilling] = useState(false);

  const load = useCallback(async () => {
    try {
      const v = await api.portal(token);
      setView(v);
      setError(null);
      if (v.form) setForm((f) => f ?? normalizeForm(v.form));
      return v;
    } catch (e) {
      setError((e as Error).message);
      return null;
    }
  }, [token]);

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    if (!view?.scenario_id) return;
    api.scenarios().then((r) => setHasFix(!!r.scenarios.find((s) => s.id === view.scenario_id)?.fix)).catch(() => undefined);
  }, [view?.scenario_id]);

  useEffect(() => {
    if (!waiting) return;
    const id = window.setInterval(async () => {
      const v = await load();
      if (v && v.status !== "PROCESSING") {
        setWaiting(false);
        setForm(v.form ? normalizeForm(v.form) : null);
        setFiles({});
      }
    }, 1200);
    return () => window.clearInterval(id);
  }, [waiting, load]);

  const highlight = useMemo(() => new Set((view?.requested ?? []).map((r) => r.field).filter(Boolean) as string[]), [view]);

  const fillDemoFix = async () => {
    if (!view?.scenario_id) return;
    setFilling(true);
    try {
      const sc = (await api.scenarios()).scenarios.find((s) => s.id === view.scenario_id);
      if (!sc?.fix) return;
      setForm(normalizeForm(sc.fix.form));
      setFiles(await loadScenarioFiles(sc.fix.document_urls, sc.fix.documents));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setFilling(false);
    }
  };

  const submit = async () => {
    if (!form) return;
    setSubmitting(true);
    setError(null);
    try {
      await api.resubmit(token, form, files);
      setWaiting(true);
      setView((v) => (v ? { ...v, status: "PROCESSING", can_resubmit: false } : v));
      window.scrollTo({ top: 0, behavior: "smooth" });
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setSubmitting(false);
    }
  };

  const status: Status | null = view ? (waiting ? "PROCESSING" : view.status) : null;
  const meta = status ? STATUS_META[status] : null;
  const StatusIcon = meta?.icon ?? LoaderCircle;

  return (
    <div className="portal">
      <header className="portal-head">
        <div className="portal-brand">
          <LogoMark size={34} />
          <div>
            <strong>{config?.buyer ?? "Buyer"}</strong>
            <span>Supplier Registration Portal</span>
          </div>
        </div>
        <div className="row gap">
          {view && <span className="meta-chip mono">Ref {view.submission_id}</span>}
          <ThemeToggle compact />
        </div>
      </header>

      <main className="portal-main">
        {error && !view && (
          <EmptyState scene="not-found" title="This link isn't valid">
            {error.replace(/\.?$/, ".")} Please use the most recent link from your email, or contact the procurement team.
          </EmptyState>
        )}
        {view && status && meta && (
          <>
            <section className={`card portal-status status-${status} a-rise`}>
              <div className="portal-status-grid">
                <div className="portal-status-text">
                  <span className="eyebrow"><Lock size={12} /> Secure supplier link</span>
                  <h1>{view.legal_name}</h1>
                  <div key={status} className="portal-status-line a-rise">
                    <span className={`portal-orb orb-${meta.tone}`}>
                      <StatusIcon size={20} className={status === "PROCESSING" ? "spin" : ""} />
                    </span>
                    <p className="big">{waiting ? "Thanks! We're re-checking your updated submission. This page refreshes automatically…" : view.status_text}</p>
                  </div>
                  {status === "APPROVED" && view.vendor_code && (
                    <div className="vendor-code-big a-pop" style={delay(0.2)}>
                      <span>Your vendor code</span>
                      <strong className="mono">{view.vendor_code}</strong>
                    </div>
                  )}
                </div>
                <div className="portal-art"><PortalIllustration /></div>
              </div>
              <Stepper status={view.status} waiting={waiting} />
            </section>

              {view.can_resubmit && form && (
                <div className="a-rise" style={delay(0.1)}>
                  <div className="card asks-card">
                    <div className="card-head">
                      <div>
                        <h3>What we need from you</h3>
                        <p className="muted small">Everything else you sent is saved. Fields and documents that need attention are highlighted below.</p>
                      </div>
                      {hasFix && (
                        <button className="btn btn-sm btn-glass-brand" onClick={fillDemoFix} disabled={filling || submitting}>
                          <Wand2 size={14} /> {filling ? "Filling…" : "Demo helper: fill in the corrections"}
                        </button>
                      )}
                    </div>
                    <ol className="asks">
                      {view.requested.map((r, i) => (
                        <li key={i} className="a-slide" style={delay(0.15 + i * 0.08)}>
                          <span className="ask-num">{i + 1}</span>
                          <div>
                            {r.action}
                            {r.hint && <div className="finding-hint"><Lightbulb size={13} /> {r.hint}</div>}
                          </div>
                        </li>
                      ))}
                    </ol>
                  </div>
                  <div className="card">
                    <VendorFormFields value={form} onChange={setForm} highlight={highlight} disabled={submitting} />
                    <div className="form-section-head">
                      <span className="form-section-num">6</span>
                      <div>
                        <h3>Documents</h3>
                        <p className="muted small">Only new uploads replace documents on file.</p>
                      </div>
                    </div>
                    <DocumentSlots files={files} onChange={setFiles} required={requiredDocSlots(form)} existing={view.documents} highlight={highlight} disabled={submitting} />
                    {error && <div className="alert alert-red">{error}</div>}
                    <div className="form-footer">
                      <span className="muted small"><Lock size={12} /> Your details are sent securely to {config?.buyer ?? "the buyer"}.</span>
                      <motion.button className="btn btn-primary btn-lg" onClick={submit} disabled={submitting} whileTap={{ scale: 0.97 }}>
                        {submitting ? <><span className="spinner spinner-light" /> Sending…</> : <><Send size={16} /> Submit updates</>}
                      </motion.button>
                    </div>
                  </div>
                </div>
              )}
          </>
        )}
        {!view && !error && <EmptyState scene="loading" title="Opening your registration…" />}
      </main>
    </div>
  );
}
