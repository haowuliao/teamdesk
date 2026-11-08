import type {
  ApprovalRecord, DocumentInfo, Employee, Health, RunBrief, RunDetail, UsageSummary,
} from "../types";

const base = ""; // 走 vite proxy → 8320

async function req<T>(url: string, init?: RequestInit): Promise<{ ok: boolean; data?: T; error?: string }> {
  try {
    const r = await fetch(base + url, init);
    if (!r.ok) return { ok: false, error: `${r.status} ${await r.text().catch(() => "")}`.slice(0, 200) };
    return { ok: true, data: (await r.json()) as T };
  } catch (e) {
    return { ok: false, error: e instanceof Error ? e.message : String(e) };
  }
}

export const api = {
  health: () => req<{ ok: boolean } & Health>("/api/health").then(r => ({
    ok: r.ok && !!(r.data?.ok),
    health: r.data as Health | undefined,
    error: r.error,
  })),
  employees: () => req<{ employees: Employee[] }>("/api/employees"),
  employee: (code: string) => req<Employee & { metrics?: any }>(`/api/employees/${code}`),
  runs: (limit = 30) => req<{ runs: RunBrief[] }>(`/api/runs?limit=${limit}`),
  run: (id: string) => req<RunDetail>(`/api/runs/${id}`),
  documents: () => req<{ documents: DocumentInfo[] }>("/api/documents"),
  uploadDocument: async (file: File) => {
    const fd = new FormData();
    fd.append("file", file);
    return req<DocumentInfo>("/api/documents", { method: "POST", body: fd });
  },
  createTextTask: (text: string) =>
    req<{ run_id: string; route: string; title: string; status: string }>("/api/tasks", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ kind: "text", text }),
    }),
  createFileTask: (docId: string) =>
    req<{ run_id: string; route: string; title: string; status: string }>("/api/tasks", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ kind: "file", doc_id: docId }),
    }),
  approvalsPending: () => req<{ approvals: ApprovalRecord[] }>("/api/approvals?status=pending"),
  decideApproval: (id: string, decision: "approve" | "reject", note?: string) =>
    req<{ ok: boolean }>(`/api/approvals/${id}/decide`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ decision, note: note || "" }),
    }),
  usage: (days = 7) => req<UsageSummary>(`/api/usage/summary?days=${days}`),
};
