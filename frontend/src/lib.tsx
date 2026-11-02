import {
  Building2,
  Check,
  CircleCheck,
  CircleX,
  Clock,
  FileSearch,
  Hourglass,
  Inbox,
  Info,
  Landmark,
  Link2,
  LoaderCircle,
  Minus,
  Scale,
  ScanText,
  Send,
  ShieldAlert,
  ShieldCheck,
  TriangleAlert,
  Users,
  X,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { createContext, useContext, useEffect, useRef, useState } from "react";
import type { AppConfig, Resolution, Severity, StageStatus, Status, VendorForm } from "./types";

export const STATUS_META: Record<Status, { label: string; tone: string; short: string; icon: LucideIcon }> = {
  PROCESSING: { label: "Processing", tone: "blue", short: "Processing", icon: LoaderCircle },
  PENDING_VENDOR: { label: "Pending · awaiting vendor", tone: "amber", short: "Awaiting vendor", icon: Hourglass },
  PENDING_REVIEW: { label: "Pending · internal review", tone: "violet", short: "In review", icon: ShieldAlert },
  APPROVED: { label: "Approved", tone: "green", short: "Approved", icon: CircleCheck },
  REJECTED: { label: "Rejected", tone: "red", short: "Rejected", icon: CircleX },
};

export const STATUS_ORDER: Status[] = ["APPROVED", "PENDING_VENDOR", "PENDING_REVIEW", "REJECTED", "PROCESSING"];

export const RESOLUTION_META: Record<Exclude<Resolution, null>, { label: string; tone: string }> = {
  vendor: { label: "Vendor fix", tone: "amber" },
  review: { label: "Human review", tone: "violet" },
  reject: { label: "Disqualifying", tone: "red" },
};

export function StatusBadge({ status, large }: { status: Status; large?: boolean }) {
  const meta = STATUS_META[status] ?? { label: status, tone: "gray", icon: Info };
  const Icon = meta.icon;
  return (
    <span className={`badge tone-${meta.tone}${large ? " badge-lg" : ""}`}>
      <Icon size={large ? 15 : 13} strokeWidth={2.4} className={status === "PROCESSING" ? "spin" : ""} />
      {meta.label}
    </span>
  );
}

export function Tag({ tone, children }: { tone: string; children: React.ReactNode }) {
  return <span className={`tag tone-${tone}`}>{children}</span>;
}

export function riskTone(score: number): "green" | "amber" | "red" {
  return score >= 60 ? "red" : score >= 30 ? "amber" : "green";
}

export function RiskMeter({ score, compact }: { score: number | null | undefined; compact?: boolean }) {
  const value = Math.max(0, Math.min(100, score ?? 0));
  const tone = riskTone(value);
  const band = value >= 60 ? "High" : value >= 30 ? "Medium" : "Low";
  return (
    <div className={`risk ${compact ? "risk-compact" : ""}`} title={`Risk ${value}/100`}>
      <div className="risk-track">
        <div className={`risk-fill fill-${tone}`} style={{ width: `${Math.max(value, 3)}%` }} />
      </div>
      <span className={`risk-label text-${tone}`}>{compact ? value : `${band} · ${value}/100`}</span>
    </div>
  );
}

const SEVERITY_ICON: Record<Severity | StageStatus, LucideIcon | null> = {
  pass: Check,
  info: Info,
  warn: TriangleAlert,
  fail: X,
  pending: null,
  running: null,
  skipped: Minus,
  error: X,
};

export function StatusDot({ status, size = 24 }: { status: Severity | StageStatus; size?: number }) {
  if (status === "running") {
    return (
      <span className="dot dot-running" style={{ width: size, height: size }}>
        <span className="dot-pulse" />
        <LoaderCircle size={size * 0.58} className="spin" strokeWidth={2.6} />
      </span>
    );
  }
  const Icon = SEVERITY_ICON[status];
  return (
    <span key={status} className={`dot dot-${status} ${status === "pending" ? "" : "icon-pop"}`} style={{ width: size, height: size }}>
      {Icon && <Icon size={size * 0.55} strokeWidth={3} />}
    </span>
  );
}

export const STAGE_ICONS: Record<string, LucideIcon> = {
  intake: Inbox,
  format: ScanText,
  documents: FileSearch,
  consistency: Link2,
  doc_match: ShieldCheck,
  registry: Building2,
  bank: Landmark,
  duplicates: Users,
  sanctions: ShieldAlert,
  decision: Scale,
  notify: Send,
};

export function StageIcon({ stage, size = 18 }: { stage: string; size?: number }) {
  const Icon = STAGE_ICONS[stage] ?? Clock;
  return <Icon size={size} strokeWidth={2} />;
}

export function fmtTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  return d.toLocaleString(undefined, { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

export function timeAgo(iso: string | null | undefined): string {
  if (!iso) return "—";
  const s = Math.round((Date.now() - new Date(iso).getTime()) / 1000);
  if (s < 60) return `${Math.max(s, 0)}s ago`;
  if (s < 3600) return `${Math.round(s / 60)}m ago`;
  if (s < 86400) return `${Math.round(s / 3600)}h ago`;
  return `${Math.round(s / 86400)}d ago`;
}

export function duration(start: string, end: string | null): string {
  if (!end) return "—";
  const ms = new Date(end).getTime() - new Date(start).getTime();
  return ms < 1000 ? `${ms} ms` : `${(ms / 1000).toFixed(1)} s`;
}

export function usePolling<T>(fn: () => Promise<T>, intervalMs: number, deps: unknown[] = []) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const fnRef = useRef(fn);
  fnRef.current = fn;
  const [tick, setTick] = useState(0);
  useEffect(() => {
    let alive = true;
    const load = () =>
      fnRef
        .current()
        .then((d) => alive && (setData(d), setError(null)))
        .catch((e: Error) => alive && setError(e.message));
    load();
    const id = intervalMs > 0 ? window.setInterval(load, intervalMs) : undefined;
    return () => {
      alive = false;
      if (id) window.clearInterval(id);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [intervalMs, tick, ...deps]);
  return { data, error, reload: () => setTick((t) => t + 1) };
}

export const ConfigContext = createContext<AppConfig | null>(null);
export const useAppConfig = () => useContext(ConfigContext);

export function emptyForm(): VendorForm {
  return {
    company: { legal_name: "", trade_name: "", business_type: "", date_of_incorporation: "", cin: "", llpin: "", website: "" },
    address: { line1: "", line2: "", city: "", state: "", pincode: "" },
    tax: { pan: "", gstin: "", msme_registered: false, udyam_number: "" },
    bank: { account_holder_name: "", account_number: "", confirm_account_number: "", ifsc: "", bank_name: "", account_type: "Current" },
    contact: { name: "", designation: "", email: "", phone: "" },
    signatory: { name: "", designation: "" },
    declaration: { accepted: false },
  };
}

export function normalizeForm(raw: Partial<VendorForm> | null | undefined): VendorForm {
  const base = emptyForm();
  if (!raw) return base;
  const out = { ...base } as Record<string, Record<string, unknown>>;
  (Object.keys(base) as (keyof VendorForm)[]).forEach((section) => {
    const src = (raw as Record<string, Record<string, unknown> | undefined>)[section] ?? {};
    const merged: Record<string, unknown> = { ...(base[section] as Record<string, unknown>) };
    Object.keys(merged).forEach((k) => {
      const v = src[k];
      if (v !== null && v !== undefined) merged[k] = v;
    });
    out[section] = merged;
  });
  return out as unknown as VendorForm;
}

export function requiredDocSlots(form: VendorForm): string[] {
  const slots = ["gst_certificate", "pan_card", "bank_proof"];
  if (["PRIVATE_LIMITED", "PUBLIC_LIMITED", "LLP"].includes(form.company.business_type)) slots.push("incorporation_certificate");
  if (form.tax.msme_registered) slots.push("msme_certificate");
  return slots;
}
