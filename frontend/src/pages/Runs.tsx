import { useCallback, useEffect, useState } from "react";
import { api } from "../lib/api";
import { RUN_DOT, STATUS_LABEL, fmtTime } from "../lib/fmt";
import OutputRenderer from "../components/OutputRenderer";
import type { RunBrief, RunDetail } from "../types";

export default function Runs() {
  const [runs, setRuns] = useState<RunBrief[]>([]);
  const [selId, setSelId] = useState<string | null>(null);
  const [detail, setDetail] = useState<RunDetail | null>(null);
  const [loaded, setLoaded] = useState(false);

  const refreshList = useCallback(async () => {
    const r = await api.runs(40);
    if (r.ok && r.data) { setRuns(r.data.runs); setLoaded(true); }
  }, []);

  useEffect(() => {
    refreshList();
    const t = setInterval(refreshList, 3000);
    return () => clearInterval(t);
  }, [refreshList]);

  const refreshDetail = useCallback(async (id: string) => {
    const r = await api.run(id);
    if (r.ok && r.data) setDetail(r.data);
  }, []);

  useEffect(() => {
    if (!selId) { setDetail(null); return; }
    refreshDetail(selId);
    const t = setInterval(() => refreshDetail(selId), 2500);
    return () => clearInterval(t);
  }, [selId, refreshDetail]);

  return (
    <div className="mx-auto grid max-w-[1500px] gap-4 p-4 lg:grid-cols-[360px_1fr]">
      {/* 左：run 列表 */}
      <div className="panel max-h-[calc(100vh-120px)] self-start overflow-y-auto">
        <div className="border-b border-ink-700 px-4 py-2.5 text-[12px] font-medium text-slate-400">
          任务流（最近 40 条 · 3s 轮询）
        </div>
        {!loaded && <div className="px-4 py-8 text-center text-[13px] text-slate-600">加载中…</div>}
        {loaded && runs.length === 0 && <div className="px-4 py-8 text-center text-[13px] text-slate-600">还没有任务，去班组工作台发起一条吧</div>}
        <div className="divide-y divide-ink-800">
          {runs.map(r => (
            <button key={r.id} onClick={() => setSelId(r.id)}
              className={`flex w-full items-center gap-2.5 px-4 py-2.5 text-left transition-colors hover:bg-ink-800/60 ${selId === r.id ? "bg-ink-800" : ""}`}>
              <span className={`inline-block h-2 w-2 shrink-0 rounded-full ${RUN_DOT[r.status] ?? "bg-neutral-600"}`} />
              <div className="min-w-0 flex-1">
                <div className="truncate text-[13px] text-slate-200">{r.title || "(无标题)"}</div>
                <div className="mt-0.5 flex items-center gap-2 text-[11px] text-slate-500">
                  <span>{STATUS_LABEL[r.status] ?? r.status}</span>
                  <span className="font-mono">{fmtTime(r.created_at)}</span>
                  <span className="font-mono">{r.steps_done}/{r.steps_total} 步</span>
                </div>
              </div>
            </button>
          ))}
        </div>
      </div>

      {/* 右：步骤时间线 */}
      <div className="panel max-h-[calc(100vh-120px)] self-start overflow-y-auto p-4">
        {!selId && <div className="px-4 py-16 text-center text-[13px] text-slate-600">← 选择左侧任务查看执行轨迹</div>}
        {selId && !detail && <div className="px-4 py-16 text-center text-[13px] text-slate-600">加载中…</div>}
        {detail && <Timeline d={detail} />}
      </div>
    </div>
  );
}

function Timeline({ d }: { d: RunDetail }) {
  return (
    <div>
      <div className="mb-4 flex items-center gap-2.5">
        <span className={`inline-block h-2.5 w-2.5 rounded-full ${RUN_DOT[d.run.status] ?? "bg-neutral-600"}`} />
        <span className="truncate text-[15px] font-semibold text-slate-100">{d.run.title || "(无标题)"}</span>
        <span className="chip border-ink-500 bg-ink-800 text-slate-400">{STATUS_LABEL[d.run.status] ?? d.run.status}</span>
        <span className="ml-auto text-[11px] text-slate-600">{fmtTime(d.run.created_at)}{d.run.finished_at ? ` → ${fmtTime(d.run.finished_at)}` : ""}</span>
      </div>
      <div className="space-y-3">
        {d.steps.map(s => (
          <div key={s.id} className={`rounded-md border px-3.5 py-3 ${
            s.status === "error" ? "border-red-500/40 bg-red-500/5"
            : s.status === "waiting_human" ? "border-amber-500/40 bg-amber-500/5"
            : s.status === "skipped" ? "border-ink-700 bg-ink-900/40 opacity-60"
            : "border-ink-600 bg-ink-850"}`}>
            <div className="flex items-center gap-2 text-[13px]">
              <span className={`inline-block h-1.5 w-1.5 rounded-full ${RUN_DOT[s.status] ?? "bg-neutral-600"}`} />
              <span className="font-medium text-slate-200">
                {s.type === "approval" ? "人工审批" : s.type === "condition" ? "条件判断" : (s.employee_code ?? "员工")}
              </span>
              <span className="text-[11px] text-slate-500">{STATUS_LABEL[s.status] ?? s.status}</span>
              <span className="ml-auto font-mono text-[11px] text-slate-600">{s.tokens ? `${s.tokens} tok` : ""}</span>
            </div>
            {s.input_summary && <div className="mt-1.5 text-[12px] text-slate-500">输入：{s.input_summary}</div>}
            {s.reasoning && (
              <div className="mt-1.5 rounded bg-ink-900/80 px-2.5 py-1.5 font-mono text-[11px] leading-relaxed text-slate-500">
                {s.reasoning}
              </div>
            )}
            {(s.status === "completed" || s.status === "error" || s.status === "waiting_human") && (
              <div className="mt-2">
                <OutputRenderer step={s} />
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
