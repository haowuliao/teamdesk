export function fmtTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (isNaN(d.getTime())) return iso;
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
}

export function fmtTs(ts: number): string {
  const d = new Date(ts * 1000);
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
}

export function fmtPct(v: number | null | undefined): string {
  if (v == null) return "—";
  return `${Math.round(v * 1000) / 10}%`;
}

export function fmtSec(v: number | null | undefined): string {
  if (v == null) return "—";
  return `${(Math.round(v * 10) / 10).toFixed(1)}s`;
}

export const STATUS_LABEL: Record<string, string> = {
  pending: "排队中", running: "执行中", waiting_human: "等审批",
  completed: "已完成", error: "失败", skipped: "已跳过",
};

export const RUN_DOT: Record<string, string> = {
  pending: "bg-neutral-500", running: "bg-neon-cyan animate-pulse-dot", waiting_human: "bg-neon-amber animate-pulse-dot",
  completed: "bg-neon-green", error: "bg-neon-red", skipped: "bg-neutral-600",
};

export const EMP_STATUS: Record<string, { label: string; cls: string; dot: string }> = {
  standby: { label: "待命", cls: "text-neutral-400", dot: "bg-neutral-500" },
  active: { label: "执行中", cls: "text-neon-cyan", dot: "bg-neon-cyan animate-pulse-dot" },
  paused: { label: "暂停", cls: "text-neon-amber", dot: "bg-neon-amber" },
  error: { label: "异常", cls: "text-neon-red", dot: "bg-neon-red" },
};
