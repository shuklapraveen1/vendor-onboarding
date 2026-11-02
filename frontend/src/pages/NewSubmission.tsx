import { motion } from "framer-motion";
import { ArrowRight, Eraser, FlaskConical, Play, Sparkles, Star, Upload } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, loadScenarioFiles } from "../api";
import { ProgressRing } from "../components/charts";
import DocumentSlots from "../components/DocumentSlots";
import { FormIllustration } from "../components/illustrations";
import { PageHeader, delay } from "../components/motion";
import { EmptyState } from "../components/scenes";
import VendorFormFields from "../components/VendorFormFields";
import { STATUS_META, emptyForm, normalizeForm, requiredDocSlots } from "../lib";
import type { Scenario, Status, VendorForm } from "../types";

const BASE_REQUIRED = [
  "company.legal_name", "company.business_type", "address.line1", "address.city", "address.state", "address.pincode",
  "tax.pan", "tax.gstin", "bank.account_holder_name", "bank.account_number", "bank.confirm_account_number", "bank.ifsc",
  "contact.name", "contact.email", "contact.phone", "signatory.name",
];

function completeness(form: VendorForm, files: Record<string, File | null>) {
  const req = [...BASE_REQUIRED];
  const bt = form.company.business_type;
  if (bt === "PRIVATE_LIMITED" || bt === "PUBLIC_LIMITED") req.push("company.cin");
  if (bt === "LLP") req.push("company.llpin");
  if (form.tax.msme_registered) req.push("tax.udyam_number");
  const f = form as unknown as Record<string, Record<string, unknown>>;
  const filled = req.filter((p) => {
    const [s, k] = p.split(".");
    return String(f[s]?.[k] ?? "").trim() !== "";
  }).length;
  const docs = requiredDocSlots(form);
  const docsFilled = docs.filter((d) => files[d]).length;
  const decl = form.declaration.accepted ? 1 : 0;
  const total = req.length + docs.length + 1;
  return { pct: (filled + docsFilled + decl) / total, missingFields: req.length - filled, missingDocs: docs.length - docsFilled, decl };
}

function expectedTone(expected: string): string {
  const first = expected.split(/[\s→]/)[0] as Status;
  return STATUS_META[first]?.tone ?? "gray";
}

function prettyExpected(expected: string): string {
  return expected
    .split("→")
    .map((part) => {
      const key = part.trim().split(" ")[0] as Status;
      return STATUS_META[key] ? part.trim().replace(key, STATUS_META[key].short) : part.trim();
    })
    .join(" → ");
}

export default function NewSubmission() {
  const navigate = useNavigate();
  const [form, setForm] = useState<VendorForm>(emptyForm());
  const [files, setFiles] = useState<Record<string, File | null>>({});
  const [scenarios, setScenarios] = useState<Scenario[]>([]);
  const [scenariosReady, setScenariosReady] = useState(false);
  const [scenarioError, setScenarioError] = useState<string | null>(null);
  const [scenarioId, setScenarioId] = useState<string | null>(null);
  const [loading, setLoading] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    api
      .scenarios()
      .then((r) => alive && setScenarios(r.scenarios))
      .catch((e: Error) => alive && setScenarioError(e.message))
      .finally(() => alive && setScenariosReady(true));
    return () => {
      alive = false;
    };
  }, []);

  const load = async (sc: Scenario, andRun = false) => {
    setError(null);
    setLoading(sc.id);
    try {
      const loaded = await loadScenarioFiles(sc.document_urls, sc.documents);
      const nextForm = normalizeForm(sc.form);
      setForm(nextForm);
      setFiles(loaded);
      setScenarioId(sc.id);
      if (andRun) await submit(nextForm, loaded, sc.id);
      else window.scrollTo({ top: 0, behavior: "smooth" });
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(null);
    }
  };

  const submit = async (f = form, docs = files, sid = scenarioId) => {
    setSubmitting(true);
    setError(null);
    try {
      const res = await api.create(f, docs, sid);
      navigate(`/submissions/${res.submission_id}`);
    } catch (e) {
      setError((e as Error).message);
      setSubmitting(false);
    }
  };

  const clear = () => {
    setForm(emptyForm());
    setFiles({});
    setScenarioId(null);
  };

  const featured = scenarios.filter((s) => s.featured);
  const others = scenarios.filter((s) => !s.featured);
  const progress = useMemo(() => completeness(form, files), [form, files]);
  const loadedScenario = scenarios.find((s) => s.id === scenarioId);

  return (
    <div className="page">
      <PageHeader
        eyebrow={<><Upload size={13} /> Intake</>}
        title={<>New vendor <span className="grad-text">submission</span></>}
        subtitle="This is the form a vendor fills in. Incomplete submissions are accepted on purpose: the process works out what's missing and asks for it, all in one go."
        art={<FormIllustration />}
      />

      <div className="new-grid">
        <form
          className="card form-card a-rise"
          onSubmit={(e) => {
            e.preventDefault();
            submit();
          }}
        >
          <div className="form-progress">
            <ProgressRing value={progress.pct} size={52} stroke={5} tone={progress.pct >= 1 ? "green" : "brand"}>
              <strong className="small">{Math.round(progress.pct * 100)}%</strong>
            </ProgressRing>
            <div>
              <strong>{progress.pct >= 1 ? "Ready to submit" : "Submission completeness"}</strong>
              <div className="muted small">
                {progress.pct >= 1
                  ? "All mandatory fields and documents are present. The pipeline will still verify every value."
                  : `${progress.missingFields} field(s), ${progress.missingDocs} document(s)${progress.decl ? "" : " and the declaration"} outstanding. You can still submit; the process will ask for the rest.`}
              </div>
            </div>
          </div>

          {loadedScenario && (
            <div key={loadedScenario.id} className="alert alert-brand row between scenario-loaded a-fade">
              <span><Sparkles size={14} /> Loaded demo scenario <strong>{loadedScenario.title}</strong>. Edit anything before submitting.</span>
              <button type="button" className="btn btn-sm btn-ghost" onClick={clear}>Clear</button>
            </div>
          )}

          <VendorFormFields value={form} onChange={setForm} disabled={submitting} />

          <div className="form-section-head">
            <span className="form-section-num">6</span>
            <div>
              <h3>Documents</h3>
              <p className="muted small">PDF only, max 5 MB each. Documents are read and classified by content, so a file in the wrong slot is caught.</p>
            </div>
          </div>
          <DocumentSlots files={files} onChange={setFiles} required={requiredDocSlots(form)} disabled={submitting} />
          {error && <div className="alert alert-red">{error}</div>}
          <div className="form-footer">
            <button type="button" className="btn btn-ghost" onClick={clear} disabled={submitting}><Eraser size={15} /> Reset form</button>
            <motion.button type="submit" className="btn btn-primary btn-lg" disabled={submitting} whileTap={{ scale: 0.97 }}>
              {submitting ? <><span className="spinner spinner-light" /> Submitting…</> : <>Submit & run checks <ArrowRight size={17} /></>}
            </motion.button>
          </div>
        </form>

        <aside className="scenario-panel a-rise" style={delay(0.1)}>
          <div className="card scenario-card">
            <div className="scenario-panel-head">
              <span className="scenario-panel-icon"><FlaskConical size={18} /></span>
              <div>
                <h3>Demo scenarios</h3>
                <p className="muted small">Realistic fictional vendors with generated PDFs. <strong>Load</strong> fills the form so you can inspect it; <strong>Run</strong> submits immediately.</p>
              </div>
            </div>
            {!scenariosReady && <EmptyState card={false} compact scene="loading" title="Loading demo scenarios…" />}
            {scenariosReady && scenarios.length === 0 && (
              <EmptyState card={false} compact scene="documents" title={scenarioError ? "Couldn't load demo scenarios" : "No demo scenarios available"}>
                {scenarioError ?? "Scenario PDFs are generated when the backend starts. Restart ./start.sh to regenerate them."} You can still fill in the form by hand.
              </EmptyState>
            )}
            {[["Featured", featured], ["More edge cases", others]].filter(([, items]) => (items as Scenario[]).length > 0).map(([title, items]) => (
              <div key={title as string}>
                <h4 className="scenario-group">{title === "Featured" && <Star size={12} />}{title as string}</h4>
                {(items as Scenario[]).map((sc, i) => (
                  <div
                    key={sc.id}
                    className={`scenario a-rise ${scenarioId === sc.id ? "scenario-active" : ""}`}
                    style={delay(0.15 + i * 0.05)}
                  >
                    <div className="scenario-top">
                      <span className="scenario-num mono">{sc.id.slice(0, 2)}</span>
                      <div className="scenario-title">{sc.title}</div>
                    </div>
                    <div className="muted small">{sc.company}</div>
                    <div className="scenario-expected">
                      <span className="muted">Expected</span>
                      <span className={`tag tone-${expectedTone(sc.expected)}`}>{prettyExpected(sc.expected)}</span>
                    </div>
                    <p className="small">{sc.description}</p>
                    <div className="row gap">
                      <button type="button" className="btn btn-sm btn-ghost" disabled={!!loading || submitting} onClick={() => load(sc)}>
                        {loading === sc.id ? "Loading…" : "Load"}
                      </button>
                      <button type="button" className="btn btn-sm btn-primary" disabled={!!loading || submitting} onClick={() => load(sc, true)}>
                        <Play size={12} fill="currentColor" /> Run
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            ))}
          </div>
        </aside>
      </div>
    </div>
  );
}
