// TeamDesk 前端类型 —— 字段全部来自 8320 实测 API（PLAN §6）
export interface Metrics {
  tasks_total: number;
  tasks_today: number;
  success_rate: number | null;
  avg_seconds: number | null;
  errors: number;
  tokens_in: number;
  tokens_out: number;
  cost_est: number;
}

export interface Permissions {
  autonomous: string[];
  approval_required: string[];
  forbidden: string[];
}

export interface Employee {
  id: string;
  code: string;
  name: string;
  emoji: string;
  title: string;
  jd: string;
  permissions: Permissions;
  model: string | null;
  status: "standby" | "active" | "paused" | "error";
  created_at: string;
  metrics: Metrics;
  persona?: string;
}

export interface RunBrief {
  id: string;
  title: string;
  trigger: "chat" | "upload";
  status: "pending" | "running" | "waiting_human" | "completed" | "error" | "skipped";
  reason: string | null;
  created_at: string;
  finished_at: string | null;
  parent_id: string | null;
  steps_total: number;
  steps_done: number;
}

export interface Step {
  id: string;
  idx: number;
  type: "employee" | "approval" | "condition";
  employee_id: string | null;
  employee_code: string | null;
  input_summary: string | null;
  output: any;
  reasoning: string | null;
  status: "pending" | "running" | "completed" | "error" | "skipped" | "waiting_human";
  tokens: number;
  started_at: string | null;
  finished_at: string | null;
  flag_key: string | null;
  skip_targets: string[] | null;
}

export interface ApprovalRecord {
  id: string;
  run_id: string;
  step_id: string;
  run_title?: string;
  employee_code?: string;
  payload: { risk_note?: string; payload?: { action?: string; recipient?: string } } & Record<string, any>;
  risk_note: string;
  status: "pending" | "approved" | "rejected";
  decided_by: string | null;
  note: string;
  decided_at: string | null;
}

export interface BusEvent {
  type: string;
  run_id?: string;
  employee_id?: string | null;
  ts: number;
  payload: Record<string, any>;
}

export interface RunDetail {
  run: RunBrief;
  steps: Step[];
  approvals: ApprovalRecord[];
  events: BusEvent[];
}

export interface DocumentInfo {
  id: string;
  filename: string;
  kind: string;
  size: number;
  rows: number | null;
  text_preview: string;
  indexed: boolean;
  created_at: string;
}

export interface Health {
  ok: boolean;
  llm_online: boolean;
  model: string;
  embed_mode: string;
  offline_mode: boolean;
}

export interface UsageSummary {
  window_days: number;
  totals: { tokens_in: number; tokens_out: number; cost_est: number; calls: number };
  trend: { date: string; tokens: number; cost_est: number; calls: number }[];
  per_employee: {
    code: string; name: string; emoji: string; title: string;
    tokens_in: number; tokens_out: number; cost_est: number;
    tasks: number; success_rate: number | null; avg_seconds: number | null;
  }[];
  recent: { id: string; ts: string; employee_code: string | null; model: string | null; tokens_in: number; tokens_out: number; cost_est: number }[];
}
