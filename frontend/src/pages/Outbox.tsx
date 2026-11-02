import { motion } from "framer-motion";
import { ExternalLink, Mails } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api";
import { MailIllustration } from "../components/illustrations";
import { PageHeader, delay } from "../components/motion";
import { EmptyState } from "../components/scenes";
import { Tag, fmtTime, usePolling } from "../lib";

const KIND_TONE: Record<string, string> = {
  info_request: "amber",
  approval: "green",
  rejection: "red",
  under_review: "blue",
  review_alert: "violet",
};

const AUDIENCES = [
  { key: "all", label: "All" },
  { key: "vendor", label: "To vendors" },
  { key: "internal", label: "Internal" },
] as const;

export default function Outbox() {
  const { data, error } = usePolling(() => api.outbox(), 3000);
  const [selected, setSelected] = useState<number | null>(null);
  const [audience, setAudience] = useState<"all" | "vendor" | "internal">("all");
  const all = data ?? [];
  const items = all.filter((m) => audience === "all" || m.audience === audience);
  const msg = items.find((m) => m.id === selected) ?? items[0];

  let body;
  if (!data) {
    body = !error && <EmptyState scene="loading" title="Loading the outbox…" />;
  } else if (all.length === 0) {
    body = (
      <EmptyState
        scene="inbox"
        title="No messages yet"
        action={<Link to="/new" className="btn btn-primary">Run a demo scenario</Link>}
      >
        Every email the process drafts lands here: requests for corrections, approvals, rejections and internal review alerts.
      </EmptyState>
    );
  } else if (items.length === 0) {
    body = (
      <EmptyState scene="no-match" title={audience === "vendor" ? "No vendor emails yet" : "No internal alerts yet"}>
        {audience === "vendor"
          ? "Nothing has been sent to a vendor so far."
          : "Internal alerts are raised only when a case needs a reviewer, e.g. a bank-account mismatch or a watchlist match."}
      </EmptyState>
    );
  } else {
    body = (
      <div className="outbox">
        <ul className="card outbox-list">
          {items.map((m, i) => (
            <motion.li
              key={m.id}
              layout="position"
              className={`a-slide ${msg?.id === m.id ? "active" : ""}`}
              style={delay(Math.min(i, 12) * 0.025)}
              onClick={() => setSelected(m.id)}
            >
              {msg?.id === m.id && <motion.span layoutId="outbox-active" className="outbox-active-bg" transition={{ type: "spring", stiffness: 500, damping: 40 }} />}
              <div className="row between">
                <Tag tone={KIND_TONE[m.kind] ?? "gray"}>{m.kind.replace("_", " ")}</Tag>
                <span className="muted small">{fmtTime(m.created_at)}</span>
              </div>
              <div className="strong small">{m.subject}</div>
              <div className="muted small">{m.to_address}</div>
            </motion.li>
          ))}
        </ul>
        {msg && (
          <article key={msg.id} className="card outbox-view a-fade">
            <div className="outbox-view-head">
              <div className={`mail-avatar tone-${KIND_TONE[msg.kind] ?? "gray"}`}>{msg.audience === "vendor" ? "V" : "R"}</div>
              <div className="outbox-view-title">
                <h3>{msg.subject}</h3>
                <div className="muted small">To: {msg.to_address} · drafted by {msg.engine} · case <Link to={`/submissions/${msg.submission_id}`}>{msg.submission_id}</Link></div>
              </div>
              {msg.action_url && (
                <a className="btn btn-primary btn-sm" href={msg.action_url.replace(/^https?:\/\/[^/]+/, "")} target="_blank" rel="noreferrer">
                  {msg.audience === "vendor" ? "Open as vendor" : "Open case"} <ExternalLink size={13} />
                </a>
              )}
            </div>
            <pre className="email">{msg.body}</pre>
          </article>
        )}
      </div>
    );
  }

  return (
    <div className="page">
      <PageHeader
        eyebrow={<><Mails size={13} /> Communication</>}
        title={<>Out<span className="grad-text">box</span></>}
        subtitle="Every email the process drafted. In production these go out via SMTP or SES; here they're stored so you can inspect them."
        actions={
          <div className="segmented" role="tablist" aria-label="Filter by audience">
            {AUDIENCES.map((a) => (
              <button key={a.key} role="tab" aria-selected={audience === a.key} className={`segmented-item ${audience === a.key ? "active" : ""}`} onClick={() => setAudience(a.key)}>
                {audience === a.key && <motion.span layoutId="outbox-seg" className="segmented-bg" transition={{ type: "spring", stiffness: 500, damping: 38 }} />}
                <span>{a.label}</span>
              </button>
            ))}
          </div>
        }
        art={<MailIllustration />}
      />
      {error && <div className="alert alert-red">{error}</div>}
      {body}
    </div>
  );
}
