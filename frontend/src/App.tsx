import { useCallback, useEffect, useMemo, useState } from "react";
import { api } from "./lib/api";
import { useBus } from "./lib/useBus";
import { EMP_STATUS } from "./lib/fmt";
import type { ApprovalRecord, Employee, Health } from "./types";
import Dashboard from "./pages/Dashboard";
import Staff from "./pages/Staff";
import Runs from "./pages/Runs";
import ConsolePage from "./pages/Console";

type PageKey = "board" | "staff" | "runs" | "console";
const NAV: { key: PageKey; label: string; icon: string }[] = [
  { key: "board", label: "班组工作台", icon: "▣" },
  { key: "staff", label: "员工档案", icon: "◉" },
  { key: "runs", label: "任务看板", icon: "☰" },
  { key: "console", label: "管理驾驶舱", icon: "◎" },
];

export default function App() {
  const [page, setPage] = useState<PageKey>("board");
  const [health, setHealth] = useState<Health | null>(null);
  const [apiDown, setApiDown] = useState(false);
  const [employees, setEmployees] = useState<Employee[]>([]);
  const [approvals, setApprovals] = useState<ApprovalRecord[]>([]);
  const { events, connected, reset } = useBus(300);

  const refreshEmployees = useCallback(async () => {
    const r = await api.employees();
    if (r.ok && r.data) { setEmployees(r.data.employees); setApiDown(false); }
  }, []);

  const refreshApprovals = useCallback(async () => {
    const r = await api.approvalsPending();
    if (r.ok && r.data) setApprovals(r.data.approvals);
  }, []);

  // health 轮询（顶栏徽标）
  useEffect(() => {
    let alive = true;
    const tick = async () => {
      const h = await api.health();
      if (!alive) return;
      if (h.ok && h.health) { setHealth(h.health); setApiDown(false); }
      else setApiDown(true);
    };
    tick();
    const t = setInterval(tick, 10000);
    return () => { alive = false; clearInterval(t); };
  }, []);

  // 员工首拉 + SSE 驱动状态灯
  useEffect(() => { refreshEmployees(); }, [refreshEmployees]);
  useEffect(() => {
    for (const ev of events) {
      if (ev.type === "employee.status" && ev.payload?.status) {
        const st = ev.payload.status as Employee["status"];
        setEmployees(prev => prev.map(e => (e.id === ev.employee_id ? { ...e, status: st } : e)));
      }
      if (ev.type === "run.status" || ev.type === "step.done") {
        setEmployees(prev => prev.map(e => (e.status === "active" ? { ...e, status: "standby" } : e)));
        refreshEmployees();
      }
      if (ev.type === "approval.pending") refreshApprovals();
      if (ev.type === "approval.decided") refreshApprovals();
      if (ev.type === "run.created") refreshEmployees();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [events]);

  // 审批 5s 兜底轮询（防止漏事件）
  useEffect(() => {
    refreshApprovals();
    const t = setInterval(refreshApprovals, 5000);
    return () => clearInterval(t);
  }, [refreshApprovals]);

  const decide = useCallback(async (id: string, decision: "approve" | "reject", note: string) => {
    await api.decideApproval(id, decision, note);
    refreshApprovals();
    refreshEmployees();
  }, [refreshApprovals, refreshEmployees]);

  const offline = !apiDown && !!health?.offline_mode;
  const modelName = health?.model ?? "—";

  return (
    <div className="flex h-full min-h-screen">
      {/* 左侧导航 */}
      <aside className="flex w-52 shrink-0 flex-col border-r border-ink-700 bg-ink-900/60">
        <div className="px-4 pb-4 pt-5">
          <div className="text-[17px] font-bold tracking-tight text-slate-100">
            Team<span className="text-neon-cyan">Desk</span>
          </div>
          <div className="mt-0.5 text-[11px] tracking-wide text-slate-500">数字班组工作台</div>
        </div>
        <nav className="flex flex-col gap-0.5 px-2">
          {NAV.map(n => (
            <button key={n.key} onClick={() => setPage(n.key)}
              className={`flex items-center gap-2.5 rounded-md px-3 py-2 text-left text-[13px] transition-colors ${
                page === n.key ? "bg-ink-700 text-slate-100" : "text-slate-400 hover:bg-ink-800 hover:text-slate-200"}`}>
              <span className={`text-[14px] ${page === n.key ? "text-neon-cyan" : ""}`}>{n.icon}</span>{n.label}
            </button>
          ))}
        </nav>
        <div className="mt-auto space-y-1.5 px-4 py-4 text-[11px] text-slate-600">
          <div className="flex items-center gap-1.5">
            <span className={`inline-block h-1.5 w-1.5 rounded-full ${connected ? "bg-neon-green" : "bg-neon-red"}`} />
            事件流 {connected ? "在线" : "重连中…"}
          </div>
          <div>v0.1 · M1 demo</div>
        </div>
      </aside>

      {/* 主区 */}
      <div className="flex min-w-0 flex-1 flex-col">
        {/* 顶栏 */}
        <header className="flex h-12 shrink-0 items-center gap-3 border-b border-ink-700 bg-ink-900/50 px-4">
          <div className="text-[13px] font-medium text-slate-300">{NAV.find(n => n.key === page)?.label}</div>
          <div className="ml-auto flex items-center gap-2">
            <span className={`chip ${apiDown ? "border-red-500/50 bg-red-500/10 text-red-300" : "border-ink-500 bg-ink-800 text-slate-400"}`}>
              后端 {apiDown ? "不可达" : "在线"}
            </span>
            <span className={`chip ${health?.llm_online ? "border-emerald-500/40 bg-emerald-500/10 text-emerald-300" : "border-ink-500 bg-ink-800 text-slate-400"}`}>
              模型 <span className="font-mono">{modelName}</span>
            </span>
          </div>
        </header>

        {(offline || apiDown) && (
          <div className={`shrink-0 px-4 py-1.5 text-[12px] ${apiDown ? "bg-red-500/15 text-red-200" : "bg-amber-500/15 text-amber-200"}`}>
            {apiDown
              ? "⚠ 后端服务（:8320）不可达 —— 请确认 uvicorn 已启动，页面将显示空态。"
              : "⚠ 离线模式：未配置 LLM API Key，员工以规则引擎 + 关键词检索运行（结果固定可复现）。配置 LLM_API_KEY 后自动升级。"}
          </div>
        )}

        <main className="min-h-0 flex-1 overflow-y-auto">
          {page === "board" && <Dashboard events={events} employees={employees} onResetFeed={reset} onEmployeesChanged={refreshEmployees} />}
          {page === "staff" && <Staff employees={employees} onChanged={refreshEmployees} />}
          {page === "runs" && <Runs />}
          {page === "console" && <ConsolePage />}
        </main>
      </div>

      {/* 审批浮层 */}
      {approvals.length > 0 && (
        <div className="fixed right-4 top-14 z-50 w-[380px] space-y-2">
          {approvals.map(a => (
            <ApprovalCard key={a.id} a={a} onDecide={decide} />
          ))}
        </div>
      )}
    </div>
  );
}

function ApprovalCard({ a, onDecide }: { a: ApprovalRecord; onDecide: (id: string, d: "approve" | "reject", note: string) => void }) {
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const emp = a.employee_code ? EMP_STATUS.standby : null;
  const meta = useMemo(() => a.payload?.payload ?? {}, [a]);
  const act = async (d: "approve" | "reject") => {
    setBusy(true);
    await onDecide(a.id, d, note.trim());
    setBusy(false);
  };
  return (
    <div className="panel animate-[slidein_.25s_ease-out] border-amber-500/40 shadow-xl shadow-amber-950/40">
      <style>{`@keyframes slidein { from { opacity:0; transform: translateX(24px);} to {opacity:1; transform:none;} }`}</style>
      <div className="flex items-center gap-2 border-b border-ink-600 px-4 py-2.5">
        <span className="inline-block h-2 w-2 animate-pulse-dot rounded-full bg-neon-amber" />
        <span className="text-[13px] font-semibold text-amber-200">审批请求</span>
        {a.employee_code && <span className="chip ml-auto border-amber-500/40 bg-amber-500/10 text-amber-300">{a.employee_code} · {a.run_title}</span>}
      </div>
      <div className="space-y-2 px-4 py-3 text-[13px] text-slate-300">
        <div>{a.risk_note || "（无风险说明）"}</div>
        {meta.action && (
          <div className="text-[12px] text-slate-500">
            动作：<span className="font-mono text-slate-400">{meta.action}</span>
            {meta.recipient && <>　→　<span className="text-slate-400">{meta.recipient}</span></>}
          </div>
        )}
        <input value={note} onChange={e => setNote(e.target.value)} placeholder="审批备注（可选）"
          className="w-full rounded border border-ink-600 bg-ink-900 px-2.5 py-1.5 text-[12px] text-slate-300 outline-none focus:border-neon-cyan/60" />
        <div className="flex gap-2 pt-0.5">
          <button disabled={busy} onClick={() => act("approve")}
            className="flex-1 rounded-md bg-emerald-500/90 px-3 py-1.5 text-[13px] font-semibold text-emerald-950 transition hover:bg-emerald-400 disabled:opacity-50">批准</button>
          <button disabled={busy} onClick={() => act("reject")}
            className="flex-1 rounded-md border border-red-500/50 bg-red-500/10 px-3 py-1.5 text-[13px] font-semibold text-red-300 transition hover:bg-red-500/20 disabled:opacity-50">拒绝</button>
        </div>
      </div>
    </div>
  );
}
