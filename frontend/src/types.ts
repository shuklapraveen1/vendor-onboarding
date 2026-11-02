export type Status = "PROCESSING" | "PENDING_VENDOR" | "PENDING_REVIEW" | "APPROVED" | "REJECTED";
export type Severity = "pass" | "info" | "warn" | "fail";
export type Resolution = "vendor" | "review" | "reject" | null;
export type StageStatus = "pending" | "running" | "pass" | "warn" | "fail" | "info" | "skipped" | "error";

export interface VendorForm {
  company: {
    legal_name: string;
    trade_name: string;
    business_type: string;
    date_of_incorporation: string;
    cin: string;
    llpin: string;
    website: string;
  };
  address: { line1: string; line2: string; city: string; state: string; pincode: string };
  tax: { pan: string; gstin: string; msme_registered: boolean; udyam_number: string };
  bank: {
    account_holder_name: string;
    account_number: string;
    confirm_account_number: string;
    ifsc: string;
    bank_name: string;
    account_type: string;
  };
  contact: { name: string; designation: string; email: string; phone: string };
  signatory: { name: string; designation: string };
  declaration: { accepted: boolean };
}

export interface StageDef {
  key: string;
  label: string;
  description: string;
}

export interface AppConfig {
  llm: { enabled: boolean; provider: string | null; model: string | null };
  stage_delay_seconds: number;
  stages: StageDef[];
  document_slots: Record<string, string>;
  business_types: Record<string, string>;
  states: string[];
  thresholds: {
    review_risk: number;
    bank_letter_max_age_days: number;
    sanctions_review_score: number;
    sanctions_block_score: number;
  };
  buyer: string;
}

export interface Finding {
  code: string;
  stage: string;
  severity: Severity;
  title: string;
  detail: string;
  field: string | null;
  resolution: Resolution;
  vendor_action: string | null;
  hint: string | null;
  weight: number;
  blocking: boolean;
  evidence: Record<string, unknown>;
}

export interface StageResult {
  stage: string;
  label: string;
  status: StageStatus;
  counts: Record<Severity, number>;
  duration_ms: number;
}

export interface Run {
  id: string;
  submission_id: string;
  version: number;
  status: "running" | "completed" | "failed";
  started_at: string;
  finished_at: string | null;
  decision: Status | null;
  decision_reason: string | null;
  risk_score: number | null;
  findings?: Finding[] | null;
  summary?: { counts: Record<Severity, number>; stages: StageResult[]; vendor_actions: number; review_flags: number } | null;
  engine?: { llm: AppConfig["llm"]; documents: Record<string, string>; services: string[] } | null;
}

export interface Submission {
  id: string;
  created_at: string;
  updated_at: string;
  status: Status;
  legal_name: string | null;
  pan: string | null;
  gstin: string | null;
  contact_email: string | null;
  current_version: number;
  risk_score: number;
  decision_reason: string | null;
  decided_by: string | null;
  portal_token: string;
  vendor_code: string | null;
  scenario_id: string | null;
  latest_run_id?: string;
  run_count?: number;
}

export interface DocumentRecord {
  id: number;
  submission_id: string;
  version: number;
  slot: string;
  filename: string;
  sha256: string;
  size_bytes: number;
  carried_over: number;
  extraction: {
    slot_label: string;
    readable: boolean;
    classified_as: string;
    fields: Record<string, string>;
    field_sources: Record<string, string>;
    issues: string[];
    engine: string;
    pages: number;
    text_chars: number;
  } | null;
}

export interface Message {
  id: number;
  submission_id: string;
  run_id: string | null;
  created_at: string;
  audience: "vendor" | "internal";
  kind: string;
  to_address: string;
  subject: string;
  body: string;
  action_url: string | null;
  engine: string;
  legal_name?: string;
}

export interface AuditEntry {
  id: number;
  ts: string;
  actor: string;
  action: string;
  details: Record<string, unknown>;
}

export interface SubmissionDetail {
  submission: Submission;
  versions: { version: number; source: string; data: VendorForm; created_at: string }[];
  runs: Run[];
  latest_run: Run | null;
  documents: DocumentRecord[];
  messages: Message[];
  audit: AuditEntry[];
  review: { open_vendor_items: number; can_approve: boolean };
  portal_url: string;
}

export interface Scenario {
  id: string;
  title: string;
  company: string;
  featured: boolean;
  edge_case: string | null;
  expected: string;
  description: string;
  talking_points: string[];
  form: VendorForm;
  documents: Record<string, string>;
  document_urls: Record<string, string>;
  fix?: { form: VendorForm; documents: Record<string, string>; document_urls: Record<string, string> };
}

export interface RunEvent {
  seq: number;
  ts: string;
  stage: string | null;
  type: "run_started" | "stage_started" | "check" | "stage_completed" | "decision" | "message" | "run_completed";
  payload: Record<string, unknown>;
}

export interface Stats {
  total: number;
  by_status: Partial<Record<Status, number>>;
  runs_completed: number;
  avg_run_seconds: number | null;
  straight_through_rate: number | null;
  top_issues: { code: string; title: string; count: number }[];
}

export interface Vendor {
  vendor_code: string;
  legal_name: string;
  pan: string;
  gstin: string | null;
  account_number: string | null;
  ifsc: string | null;
  status: string;
  source: string;
  submission_id: string | null;
  created_at: string;
}

export interface ReviewQueueItem extends Submission {
  flags: { title: string; stage: string; code: string }[];
  open_vendor_items: number;
}

export interface PortalView {
  submission_id: string;
  legal_name: string | null;
  status: Status;
  status_text: string;
  vendor_code: string | null;
  can_resubmit: boolean;
  requested: { field: string | null; title: string; action: string; hint: string | null }[];
  form: VendorForm | null;
  documents: { slot: string; filename: string }[];
  scenario_id: string | null;
}
