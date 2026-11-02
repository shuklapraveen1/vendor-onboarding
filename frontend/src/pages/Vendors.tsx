import { Database, Search } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api";
import { DatabaseIllustration } from "../components/illustrations";
import { AnimatedNumber, PageHeader, Rise, delay } from "../components/motion";
import { EmptyState } from "../components/scenes";
import { Tag, fmtTime, usePolling } from "../lib";

const mask = (s: string | null) => (s && s.length > 4 ? "•".repeat(s.length - 4) + s.slice(-4) : s ?? "—");

export default function Vendors() {
  const { data, error } = usePolling(() => api.vendors(), 4000);
  const [q, setQ] = useState("");
  const all = data ?? [];
  const needle = q.trim().toLowerCase();
  const rows = needle
    ? all.filter((v) => [v.vendor_code, v.legal_name, v.pan, v.gstin ?? ""].some((x) => x.toLowerCase().includes(needle)))
    : all;
  const onboarded = all.filter((v) => v.source !== "erp_seed").length;

  return (
    <div className="page">
      <PageHeader
        eyebrow={<><Database size={13} /> System of record</>}
        title={<>Vendor <span className="grad-text">master</span></>}
        subtitle="The buyer's ERP vendor list. Duplicate checks run against it, and approved submissions are added to it."
        actions={
          <div className="hero-stats">
            <div><strong><AnimatedNumber value={data ? all.length : null} /></strong><span>vendors</span></div>
            <div><strong><AnimatedNumber value={data ? onboarded : null} /></strong><span>onboarded here</span></div>
          </div>
        }
        art={<DatabaseIllustration />}
      />
      {error && <div className="alert alert-red">{error}</div>}
      <Rise as="section" className="card table-card">
        <div className="card-head">
          <h3>All vendors</h3>
          <label className="search-box">
            <Search size={15} />
            <input placeholder="Search code, name, PAN, GSTIN…" value={q} onChange={(e) => setQ(e.target.value)} />
          </label>
        </div>
        {!data ? (
          !error && <EmptyState card={false} scene="loading" title="Loading the vendor master…" />
        ) : all.length === 0 ? (
          <EmptyState card={false} scene="vendors" title="The vendor master is empty">
            Approved submissions are added here automatically. Use “Reset demo data” on the dashboard to restore the seeded ERP vendors.
          </EmptyState>
        ) : rows.length === 0 ? (
          <EmptyState card={false} scene="no-match" title={`No vendors match “${q}”`} action={<button type="button" className="btn btn-ghost" onClick={() => setQ("")}>Clear search</button>}>
            Search works on vendor code, legal name, PAN and GSTIN.
          </EmptyState>
        ) : (
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr><th>Code</th><th>Legal name</th><th>PAN</th><th>GSTIN</th><th>Bank account</th><th>Source</th><th>Added</th></tr>
              </thead>
              <tbody>
                {rows.map((v, i) => (
                  <tr key={v.vendor_code} className="a-fade" style={delay(Math.min(i, 12) * 0.03)}>
                    <td><span className="id-pill mono">{v.vendor_code}</span></td>
                    <td className="strong">{v.legal_name}</td>
                    <td className="mono small">{v.pan}</td>
                    <td className="mono small">{v.gstin}</td>
                    <td className="mono small">{mask(v.account_number)} · {v.ifsc}</td>
                    <td>
                      {v.source === "erp_seed" ? <Tag tone="gray">existing ERP</Tag> : (
                        <Link to={`/submissions/${v.submission_id}`}><Tag tone="green">onboarded · {v.submission_id}</Tag></Link>
                      )}
                    </td>
                    <td className="muted small nowrap">{fmtTime(v.created_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Rise>
    </div>
  );
}
