import type {
  AppConfig,
  Message,
  PortalView,
  ReviewQueueItem,
  Run,
  Scenario,
  Stats,
  Submission,
  SubmissionDetail,
  Vendor,
  VendorForm,
} from "./types";

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, init);
  if (!res.ok) {
    let message = `${res.status} ${res.statusText}`;
    try {
      const body = await res.json();
      if (typeof body.detail === "string") message = body.detail;
      else if (Array.isArray(body.detail)) message = body.detail.map((d: { msg: string }) => d.msg).join("; ");
    } catch {
      /* non-JSON error body */
    }
    throw new ApiError(res.status, message);
  }
  return res.json() as Promise<T>;
}

function submissionBody(form: VendorForm, files: Record<string, File | null>, scenarioId?: string | null): FormData {
  const body = new FormData();
  body.append("data", JSON.stringify(form));
  Object.entries(files).forEach(([slot, file]) => {
    if (file) body.append(slot, file, file.name);
  });
  if (scenarioId) body.append("scenario_id", scenarioId);
  return body;
}

export const api = {
  config: () => request<AppConfig>("/api/config"),
  stats: () => request<Stats>("/api/stats"),
  scenarios: () => request<{ generated_on: string; scenarios: Scenario[] }>("/api/scenarios"),
  submissions: (status?: string, q?: string) => {
    const params = new URLSearchParams();
    if (status) params.set("status", status);
    if (q) params.set("q", q);
    return request<Submission[]>(`/api/submissions?${params}`);
  },
  submission: (id: string) => request<SubmissionDetail>(`/api/submissions/${id}`),
  run: (id: string) => request<Run>(`/api/runs/${id}`),
  create: (form: VendorForm, files: Record<string, File | null>, scenarioId?: string | null) =>
    request<{ submission_id: string; run_id: string }>("/api/submissions", {
      method: "POST",
      body: submissionBody(form, files, scenarioId),
    }),
  rerun: (id: string) => request<{ run_id: string }>(`/api/submissions/${id}/rerun`, { method: "POST" }),
  review: (id: string, body: { action: string; reviewer: string; note: string; vendor_note?: string }) =>
    request<{ ok: boolean; submission: Submission }>(`/api/submissions/${id}/review`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),
  reviewQueue: () => request<ReviewQueueItem[]>("/api/review-queue"),
  outbox: () => request<Message[]>("/api/outbox"),
  vendors: () => request<Vendor[]>("/api/vendors"),
  portal: (token: string) => request<PortalView>(`/api/portal/${token}`),
  resubmit: (token: string, form: VendorForm, files: Record<string, File | null>) =>
    request<{ submission_id: string; run_id: string; version: number }>(`/api/portal/${token}/resubmit`, {
      method: "POST",
      body: submissionBody(form, files),
    }),
  reset: () => request<{ ok: boolean }>("/api/admin/reset", { method: "POST" }),
};

export async function fetchAsFile(url: string, name: string): Promise<File> {
  const res = await fetch(url);
  if (!res.ok) throw new ApiError(res.status, `Could not load ${name}`);
  const blob = await res.blob();
  return new File([blob], name, { type: "application/pdf" });
}

export async function loadScenarioFiles(urls: Record<string, string>, names: Record<string, string>) {
  const entries = await Promise.all(
    Object.entries(urls).map(async ([slot, url]) => [slot, await fetchAsFile(url, names[slot])] as const),
  );
  return Object.fromEntries(entries) as Record<string, File>;
}
