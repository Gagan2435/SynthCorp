export type Column = { name: string; type: string; ref?: string };
export type TableInfo = { name: string; rows: number; columns: Column[] };
export type Edge = { from: string; to: string; column: string };
export type Plan = { order: string[]; edges: Edge[]; tables: TableInfo[] };

export type Template = { id: string; name: string; description: string; yaml: string };
export type Validation = { valid: boolean; errors: string[]; plan: Plan | null };

export type RunSummary = {
  id: number;
  name: string;
  status: "pending" | "running" | "done" | "failed";
  seed: number;
  inject_defects: boolean;
  created_at: string;
  finished_at: string | null;
  table_counts: Record<string, number> | null;
  quality_passed: number | null;
  quality_failed: number | null;
};
export type RunDetail = RunSummary & {
  plan: Plan | null;
  progress: { done_tables: string[]; total_tables: number; stage?: string } | null;
  error: string | null;
};

export type Check = {
  kind: string;
  table: string;
  column: string | null;
  description: string;
  status: "pass" | "fail";
  failed: number;
  samples: (string | number)[];
};
export type Quality = {
  total: number;
  passed: number;
  failed: number;
  checks: Check[];
  injected_defects: { table: string; column: string; defect: string; rows: number }[];
};

export type Preview = {
  table: string;
  columns: string[];
  total: number;
  limit: number;
  offset: number;
  rows: Record<string, unknown>[];
};

export class ApiError extends Error {
  details: string[];
  constructor(message: string, details: string[] = []) {
    super(message);
    this.details = details;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`/api${path}`, { ...init, headers: { "Content-Type": "application/json", ...(init?.headers || {}) } });
  if (!res.ok) {
    let details: string[] = [];
    let message = `Request failed (${res.status})`;
    try {
      const body = await res.json();
      if (body?.detail?.errors) details = body.detail.errors;
      else if (typeof body?.detail === "string") message = body.detail;
    } catch {
      /* body was not JSON */
    }
    throw new ApiError(details.length ? "The schema has problems" : message, details);
  }
  return res.status === 204 ? (undefined as T) : res.json();
}

export const api = {
  templates: () => request<Template[]>("/templates"),
  validate: (config_yaml: string) => request<Validation>("/schema/validate", { method: "POST", body: JSON.stringify({ config_yaml }) }),
  createRun: (config_yaml: string, seed: number | null, inject_defects: boolean) =>
    request<RunDetail>("/runs", { method: "POST", body: JSON.stringify({ config_yaml, seed, inject_defects }) }),
  runs: () => request<RunSummary[]>("/runs"),
  run: (id: number) => request<RunDetail>(`/runs/${id}`),
  deleteRun: (id: number) => request<void>(`/runs/${id}`, { method: "DELETE" }),
  quality: (id: number) => request<Quality>(`/runs/${id}/quality`),
  preview: (id: number, table: string, offset: number, limit = 25) =>
    request<Preview>(`/runs/${id}/tables/${table}?limit=${limit}&offset=${offset}`),
};
