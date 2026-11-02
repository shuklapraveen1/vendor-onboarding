import { Ban, Bot, CircleCheck, CircleHelp, Cpu, Hourglass, ShieldAlert, Sparkles, Wrench } from "lucide-react";
import { PipelineIllustration } from "../components/illustrations";
import { Item, PageHeader, Rise, Stagger, delay } from "../components/motion";
import { EmptyState } from "../components/scenes";
import { StageIcon, StatusBadge, useAppConfig } from "../lib";

export default function HowItWorks() {
  const config = useAppConfig();
  if (!config) return <div className="page narrow"><EmptyState scene="loading" title="Loading the process map…" /></div>;
  const t = config.thresholds;

  const routes = [
    {
      tone: "amber",
      icon: Wrench,
      title: "Vendor fix",
      meaning: "The vendor can correct it themselves",
      examples: `Missing field or document, GSTIN typo, GSTIN from another state, wrong file uploaded, bank letter older than ${t.bank_letter_max_age_days} days`,
      status: "PENDING_VENDOR" as const,
    },
    {
      tone: "violet",
      icon: ShieldAlert,
      title: "Human review",
      meaning: "A fraud or compliance signal that needs judgement",
      examples: `Bank account belongs to someone else, existing vendor's PAN reused, possible watchlist match (score ≥ ${t.sanctions_review_score}), GSTIN registered to another entity`,
      status: "PENDING_REVIEW" as const,
    },
    {
      tone: "red",
      icon: Ban,
      title: "Disqualifying",
      meaning: "Can't be fixed by the vendor or overridden by a reviewer",
      examples: `GST cancelled, company struck off, exact duplicate of an existing vendor, confirmed watchlist match (score ≥ ${t.sanctions_block_score} and same country or identifier)`,
      status: "REJECTED" as const,
    },
  ];

  const ladder = [
    { tone: "red", icon: Ban, cond: "Any disqualifying finding", out: "Rejected" },
    { tone: "violet", icon: ShieldAlert, cond: "Any review signal (vendor-fixable items are held)", out: "Pending review" },
    { tone: "amber", icon: Hourglass, cond: "Any vendor-fixable failure", out: "Pending vendor" },
    { tone: "violet", icon: Sparkles, cond: `Minor warnings add up to risk ≥ ${t.review_risk}`, out: "Pending review" },
    { tone: "green", icon: CircleCheck, cond: "Otherwise", out: "Approved" },
  ];

  return (
    <div className="page narrow">
      <PageHeader
        eyebrow={<><CircleHelp size={13} /> Plain-language guide</>}
        title={<>How it <span className="grad-text">works</span></>}
        subtitle={`Every submission goes through all ${config.stages.length} stages, so the vendor gets one complete list of fixes instead of one problem at a time.`}
        art={<PipelineIllustration />}
      />

      <Rise as="section" className="card">
        <h3 className="section-h"><span className="section-n">1</span> Process map</h3>
        <Stagger as="ol" className="process-map">
          {config.stages.map((s, i) => (
            <Item as="li" key={s.key}>
              <span className="pm-num">{i + 1}</span>
              <span className="pm-icon"><StageIcon stage={s.key} size={18} /></span>
              <div>
                <strong>{s.label}</strong>
                <div className="muted small">{s.description}</div>
              </div>
            </Item>
          ))}
        </Stagger>
      </Rise>

      <Rise as="section" className="card" delay={0.08}>
        <h3 className="section-h"><span className="section-n">2</span> Every check routes to one of three owners</h3>
        <div className="route-cards">
          {routes.map((r, i) => (
            <div key={r.title} className={`route-card route-${r.tone} a-rise`} style={delay(0.1 + i * 0.1)}>
              <span className={`route-icon tone-${r.tone}`}><r.icon size={20} /></span>
              <h4>{r.title}</h4>
              <p className="route-meaning">{r.meaning}</p>
              <p className="small muted">{r.examples}</p>
              <StatusBadge status={r.status} />
            </div>
          ))}
        </div>

        <h4 className="ladder-title">Order of rules</h4>
        <ol className="ladder">
          {ladder.map((l, i) => (
            <li key={i} className="a-slide" style={delay(0.2 + i * 0.08)}>
              <span className={`ladder-icon tone-${l.tone}`}><l.icon size={16} /></span>
              <span className="ladder-cond">{l.cond}</span>
              <span className="ladder-arrow" aria-hidden>→</span>
              <span className={`tag tone-${l.tone}`}>{l.out}</span>
            </li>
          ))}
        </ol>
      </Rise>

      <Rise as="section" className="card" delay={0.12}>
        <h3 className="section-h"><span className="section-n">3</span> Where AI is used, and where it deliberately isn't</h3>
        <div className="two-col">
          <div className="ai-col ai-yes">
            <h4><Bot size={16} /> AI helps with</h4>
            <ul className="check-list">
              <li>Reading fields from documents whose layout the parser doesn't know. Its output is re-validated (checksums, formats), and anything invalid is discarded.</li>
              <li>Classifying documents the keyword classifier can't identify.</li>
              <li>Writing the friendly opening paragraph of vendor emails.</li>
            </ul>
          </div>
          <div className="ai-col ai-no">
            <h4><Ban size={16} /> AI never</h4>
            <ul className="check-list">
              <li>Decides approve, pending or reject. Decisions are deterministic, explainable and auditable.</li>
              <li>Writes the list of what the vendor must fix. That always comes from the findings.</li>
              <li>Sees fraud signals when writing vendor emails.</li>
            </ul>
          </div>
        </div>
        <div className="mode-pill">
          {config.llm.enabled ? <Bot size={15} /> : <Cpu size={15} />}
          Current mode: {config.llm.enabled ? <strong>AI assist on ({config.llm.provider} · {config.llm.model})</strong> : <strong>rules and parsers only (no API key set). Everything still works end to end.</strong>}
        </div>
      </Rise>

      <Rise as="section" className="card" delay={0.16}>
        <h3 className="section-h"><span className="section-n">4</span> Assumptions in this build</h3>
        <ul className="check-list small">
          <li>The buyer is an Indian company onboarding Indian vendors: GSTIN, PAN, CIN, IFSC and Udyam rules apply.</li>
          <li>The GST portal, MCA registry, IFSC directory, penny-drop bank verification and sanctions list are <strong>mocks with seeded data</strong>, behind the same interfaces a real integration would use. Identifiers that aren't seeded get a simulated "OK" so ad-hoc demo inputs still run end to end, and this is flagged as an info finding.</li>
          <li>Emails are drafted into the outbox rather than sent. The vendor portal link is real and works on localhost.</li>
          <li>The watchlist entries are fictional.</li>
          <li>Documents must be text-based PDFs. Scanned images are detected and the vendor is asked for a clearer copy (OCR is listed as next work).</li>
        </ul>
      </Rise>
    </div>
  );
}
