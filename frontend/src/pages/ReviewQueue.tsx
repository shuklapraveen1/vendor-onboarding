import { ArrowRight, Clock, ShieldAlert } from "lucide-react";
import { Link } from "react-router-dom";
import { api } from "../api";
import { RiskGauge } from "../components/charts";
import { ReviewIllustration } from "../components/illustrations";
import { PageHeader, delay } from "../components/motion";
import { EmptyState } from "../components/scenes";
import { StageIcon, Tag, timeAgo, usePolling } from "../lib";

const STAGE_TONE: Record<string, string> = { sanctions: "red", bank: "violet", duplicates: "amber", registry: "blue" };

export default function ReviewQueue() {
  const { data, error } = usePolling(() => api.reviewQueue(), 3000);
  const items = (data ?? []).slice().sort((a, b) => b.risk_score - a.risk_score);
  return (
    <div className="page">
      <PageHeader
        eyebrow={<><ShieldAlert size={13} /> Human in the loop</>}
        title={<>Review <span className="grad-text">queue</span></>}
        subtitle="Cases the rules engine won't decide alone: fraud signals, watchlist near-matches and registry conflicts. Highest risk first."
        art={<ReviewIllustration />}
      />
      {error && <div className="alert alert-red">{error}</div>}
      {!data && !error && <EmptyState scene="loading" title="Loading the review queue…" />}
      {data && items.length === 0 && (
        <EmptyState scene="all-clear" title="All clear — nothing needs a human" action={<Link to="/new" className="btn btn-ghost">Try scenario 05 or 07 to see a flagged case</Link>}>
          The rules engine routes a case here only for fraud signals, watchlist near-matches or registry conflicts. New flags appear automatically.
        </EmptyState>
      )}
      <div className="queue">
        {items.map((item, i) => (
            <div key={item.id} className="a-rise" style={delay(Math.min(i, 10) * 0.05)}>
              <Link to={`/submissions/${item.id}`} className="card queue-item">
                <div className="queue-top">
                  <div className="queue-rank">#{i + 1}</div>
                  <div className="queue-title">
                    <div className="strong">{item.legal_name}</div>
                    <div className="muted small mono">{item.id} · {item.gstin}</div>
                  </div>
                  <RiskGauge score={item.risk_score} />
                </div>
                <ul className="queue-flags">
                  {item.flags.map((f, n) => (
                    <li key={n}>
                      <Tag tone={STAGE_TONE[f.stage] ?? "gray"}><StageIcon stage={f.stage} size={11} /> {f.stage}</Tag>
                      <span>{f.title}</span>
                    </li>
                  ))}
                </ul>
                <div className="queue-foot">
                  <span>{item.open_vendor_items > 0 ? `${item.open_vendor_items} vendor-fixable item(s) held` : "No vendor items outstanding"}</span>
                  <span className="queue-go"><Clock size={13} /> waiting {timeAgo(item.updated_at)} <ArrowRight size={14} /></span>
                </div>
              </Link>
            </div>
        ))}
      </div>
    </div>
  );
}
