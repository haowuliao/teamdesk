import { useEffect, useMemo, useRef, useState } from "react";
import { api } from "../lib/api";
import { EMP_STATUS, fmtTs } from "../lib/fmt";
import type { BusEvent, Employee } from "../types";

export default function Dashboard({ events, employees, onResetFeed, onEmployeesChanged }: {
  events: BusEvent[];
  employees: Employee[];
  onResetFeed: () => void;
  onEmployeesChanged: () => void;
}) {
  return (
    <div className="mx-auto max-w-[1500px] space-y-4 p-4">
      <EmployeeLights employees={employees} />
      <div className="grid gap-4 lg:grid-cols-[1fr_420px]">
        <TaskLauncher onLaunched={onEmployeesChanged} />
        <EventFeed events={events} onClear={onResetFeed} />
      </div>
    </div>
  );
}

/* ---------------- 员工状态灯行 ---------------- */
function EmployeeLights({ employees }: { employees: Employee[] }) {
  if (employees.length === 0) {
    return <div className="panel px-4 py-8 text-center text-[13px] text-slate-600">正在加载班组…（后端不可用时此处为空）</div>;
  }
  return (
    <div className="grid grid-cols-2 gap-3 md:grid-cols-5">
      {employees.map(e => {
        const st = EMP_STATUS[e.status] ?? EMP_STATUS.standby;
        const active = e.status === "active";
        return (
          <div key={e.id}
            className={`panel relative px-3.5 py-3 transition-colors ${active ? "border-cyan-500/50 bg-cyan-500/5" : ""}`}>
            <div className="flex items-center gap-2.5">
              <span className={`text-[22px] ${active ? "animate-pulse-dot" : ""}`}>{e.emoji}</span>
              <div className="min-w-0">
                <div className="truncate text-[13px] font-semibold text-slate-200">
                  {e.name}
                  <span className="ml-1.5 font-mono text-[10px] text-slate-600">{e.code}</span>
                </div>
                <div className="truncate text-[11px] text-slate-500">{e.title}</div>
              </div>
              <span className={`ml-auto inline-block h-2 w-2 shrink-0 rounded-full ${st.dot}`} />
            </div>
            <div className="mt-2 flex items-center justify-between text-[11px] text-slate-500">
              <span className={st.cls}>{st.label}</span>
              <span>今日 <span className="font-mono text-slate-300">{e.metrics.tasks_today}</span> 件</span>
            </div>
          </div>
        );
      })}
    </div>
  );
}

/* ---------------- 任务发起器 ---------------- */
const EXT_OK = [".xlsx", ".csv", ".pdf", ".txt", ".md"];

function TaskLauncher({ onLaunched }: { onLaunched: () => void }) {
  const [text, setText] = useState("");
  const [drag, setDrag] = useState(false);
  const [busy, setBusy] = useState(false);
  const [log, setLog] = useState<{ t: string; ok: boolean } | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  const say = (t: string, ok: boolean) => setLog({ t, ok });

  async function launchFile(file: File) {
    const ext = "." + (file.name.split(".").pop() || "").toLowerCase();
    if (!EXT_OK.includes(ext)) { say(`不支持的文件类型 ${ext}（支持 ${EXT_OK.join(" ")}）`, false); return; }
    setBusy(true); say("上传文件中…", true);
    const up = await api.uploadDocument(file);
    if (!up.ok || !up.data) { setBusy(false); say(`上传失败：${up.error ?? "未知错误"}`, false); return; }
    say(`${file.name} 已入库（${up.data.kind}${up.data.rows != null ? `，${up.data.rows} 行` : ""}）→ 发起任务…`, true);
    const tk = await api.createFileTask(up.data.id);
    setBusy(false);
    if (tk.ok && tk.data) say(`任务已创建，路由 → ${tk.data.route}`, true);
    else { say(`任务创建失败：${tk.error ?? ""}`, false); return; }
    onLaunched();
  }

  function launchText() {
    const t = text.trim();
    if (!t) return;
    setBusy(true);
    api.createTextTask(t).then(tk => {
      setBusy(false);
      if (tk.ok && tk.data) { say(`提问已发出，路由 → ${tk.data.route}`, true); setText(""); onLaunched(); }
      else say(`提交失败：${tk.error ?? ""}`, false);
    });
  }

  return (
    <div className="panel flex min-h-[420px] flex-col">
      <div className="panel-title"><span className="text-neon-cyan">▶</span> 任务发起器</div>
      <div className="flex flex-1 flex-col gap-3 p-4 pt-1">
        {/* 拖拽上传 */}
        <div
          onDragOver={e => { e.preventDefault(); setDrag(true); }}
          onDragLeave={() => setDrag(false)}
          onDrop={e => {
            e.preventDefault(); setDrag(false);
            const f = e.dataTransfer.files?.[0];
            if (f) launchFile(f);
          }}
          onClick={() => fileRef.current?.click()}
          className={`flex cursor-pointer flex-col items-center justify-center rounded-lg border-2 border-dashed px-4 py-8 text-center transition-colors ${
            drag ? "border-cyan-400/80 bg-cyan-500/10" : "border-ink-500 bg-ink-900/40 hover:border-ink-500/80 hover:bg-ink-800/60"}`}>
          <div className="text-[26px]">⬆</div>
          <div className="mt-1.5 text-[13px] text-slate-400">拖入文件（xlsx / csv / pdf / txt / md）或点击选择</div>
          <div className="mt-0.5 text-[11px] text-slate-600">系统会自动把文件交给对口的数字员工</div>
          <input ref={fileRef} type="file" accept={EXT_OK.join(",")} className="hidden"
            onChange={e => { const f = e.target.files?.[0]; if (f) launchFile(f); e.currentTarget.value = ""; }} />
        </div>

        <div className="mx-auto h-px w-2/3 bg-ink-600" />
        <div className="text-center text-[11px] tracking-widest text-slate-600">或直接提问</div>

        {/* 文本提问 */}
        <textarea
          value={text}
          onChange={e => setText(e.target.value)}
          onKeyDown={e => { if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) launchText(); }}
          rows={3}
          placeholder="例如：破损包裹怎么理赔？／ 退款运费谁承担？"
          className="w-full resize-none rounded-lg border border-ink-600 bg-ink-900/70 px-3 py-2.5 text-[13px] text-slate-200 outline-none placeholder:text-slate-600 focus:border-cyan-500/60" />
        <div className="flex items-center gap-2">
          <button onClick={launchText} disabled={busy || !text.trim()}
            className="rounded-md bg-cyan-500/90 px-5 py-2 text-[13px] font-semibold text-cyan-950 transition hover:bg-cyan-400 disabled:cursor-not-allowed disabled:opacity-40">
            {busy ? "派发中…" : "派发任务"}
          </button>
          <span className="text-[11px] text-slate-600">Ctrl/⌘ + Enter</span>
        </div>

        {log && (
          <div className={`mt-auto rounded-md border px-3 py-2 font-mono text-[12px] ${log.ok ? "border-emerald-500/30 bg-emerald-500/5 text-emerald-300/90" : "border-red-500/40 bg-red-500/10 text-red-300"}`}>
            {log.t}
          </div>
        )}
      </div>
    </div>
  );
}

/* ---------------- 实时事件流（SSE，按 run 分组折叠） ---------------- */
interface FeedEntry { ev: BusEvent; key: number }

function EventFeed({ events, onClear }: { events: BusEvent[]; onClear: () => void }) {
  const groups = useMemo(() => {
    const m = new Map<string, FeedEntry[]>();
    let k = 0;
    for (const ev of events) {
      if (ev.type === "connected") continue;
      const g = ev.run_id || "global";
      if (!m.has(g)) m.set(g, []);
      m.get(g)!.push({ ev, key: k++ });
    }
    return Array.from(m.entries());
  }, [events]);

  const newestRun = groups[groups.length - 1]?.[0];

  return (
    <div className="panel flex min-h-[420px] flex-col">
      <div className="panel-title">
        <span className="text-neon-green">≋</span> 实时事件流
        <button onClick={onClear} className="ml-auto rounded border border-ink-600 px-2 py-0.5 text-[11px] normal-case text-slate-500 hover:text-slate-300">清空</button>
      </div>
      <div className="min-h-0 flex-1 space-y-2 overflow-y-auto p-3 pt-1">
        {groups.length === 0 && (
          <div className="pt-10 text-center text-[12px] text-slate-600">等待事件…（发起任务或上传文件后这里会滚动）</div>
        )}
        {groups.map(([gid, items]) => (
          <details key={gid} open={gid === newestRun} className="group rounded-md border border-ink-700 bg-ink-900/50">
            <summary className="flex cursor-pointer select-none items-center gap-2 px-3 py-2 text-[12px] text-slate-400 hover:text-slate-200">
              <span className="font-mono text-[10px] text-slate-600">{gid === "global" ? "SYS" : gid.slice(0, 8) + "…"}</span>
              <span className="truncate">{headline(items[items.length - 1].ev) ?? headline(items[0].ev)}</span>
              <span className="ml-auto font-mono text-[10px] text-slate-600">{items.length} 条</span>
            </summary>
            <div className="space-y-1.5 border-t border-ink-700 px-3 py-2">
              {items.map(({ ev, key }) => <FeedRow key={key} ev={ev} last={key === items[items.length - 1].key} />)}
            </div>
          </details>
        ))}
      </div>
    </div>
  );
}

function headline(ev: BusEvent): string | null {
  const p = ev.payload || {};
  switch (ev.type) {
    case "run.created": return `新任务「${p.title}」→ 路由 ${p.route}`;
    case "run.status":
      if (p.resumed) return "审批通过，续跑中";
      return p.status === "completed" ? "任务完成 ✓" : p.status === "waiting_human" ? "等待人工审批" : `状态：${p.status}${p.reason ? `（${p.reason}）` : ""}`;
    case "step.started": return `${p.code ?? ""} 开始执行`;
    case "step.output": return `${p.code ?? ""} 产出结果`;
    case "step.done": return `${p.code ?? ""} ${p.status === "error" ? "执行失败" : "步骤结束"}`;
    case "approval.pending": return "需要审批：对外发送";
    case "approval.decided": return `审批${p.decision === "approve" ? "通过" : "拒绝"}（${p.decided_by}）`;
    case "employee.status": return `${p.status}`;
    default: return ev.type;
  }
}

function FeedRow({ ev, last }: { ev: BusEvent; last: boolean }) {
  const p = ev.payload || {};
  const isThinking = ev.type === "step.output";
  return (
    <div className="flex gap-2 text-[12px] leading-relaxed">
      <span className="shrink-0 font-mono text-[10px] text-slate-600">{fmtTs(ev.ts)}</span>
      <div className="min-w-0 flex-1">
        <span className={`chip mr-1.5 ${
          ev.type === "approval.pending" ? "border-amber-500/40 text-amber-300" :
          ev.type === "run.status" && (p.status === "completed") ? "border-emerald-500/40 text-emerald-300" :
          ev.type === "run.status" && p.status === "error" ? "border-red-500/40 text-red-300" :
          "border-ink-600 text-slate-500"}`}>{ev.type}</span>
        {isThinking && extractThink(p.output) ? (
          <Typewriter text={extractThink(p.output)!} active={last} />
        ) : (
          <span className="text-slate-400">{rowText(ev)}</span>
        )}
      </div>
    </div>
  );
}

function rowText(ev: BusEvent): string {
  const p = ev.payload || {};
  switch (ev.type) {
    case "run.created": return `「${p.title}」（${p.trigger === "upload" ? "上传" : "提问"}）→ 分派 ${p.route}`;
    case "step.started": return `${p.code ?? "—"} 开始处理…`;
    case "step.done": return p.status === "error" ? `${p.code ?? ""} 失败：${p.error ?? ""}` : `${p.code ?? ""} 完成（${p.status}）`;
    case "approval.pending": return p.risk_note || "等待审批";
    case "approval.decided": return `${p.decision === "approve" ? "批准" : "拒绝"}，执行人 ${p.decided_by ?? ""}`;
    case "employee.status": return `状态 → ${p.status}`;
    default: return JSON.stringify(p).slice(0, 160);
  }
}

/** 从 step.output 提取一句“思考摘要”用于打字机展示 */
function extractThink(o: any): string | null {
  if (!o || typeof o !== "object") return null;
  const pick = (arr: any) => Array.isArray(arr) && arr.length > 0 ? String(arr[0].text ?? arr[0]) : null;
  return pick(o.insights) ?? (typeof o.answer === "string" ? o.answer.slice(0, 160) : null)
    ?? (typeof o.summary === "string" ? o.summary.slice(0, 160) : null)
    ?? (typeof o.optimized === "string" ? o.optimized.slice(0, 160) : null)
    ?? (pick(o.topics?.map?.((t: any) => ({ text: t.name ? `${t.name} ${Math.round(t.ratio * 100)}%` : String(t) }))) ?? null);
}

/** 打字机：仅最新一条推理文本逐字显现 */
function Typewriter({ text, active }: { text: string; active: boolean }) {
  const [n, setN] = useState(active ? 0 : text.length);
  const done = useRef(false);
  useEffect(() => {
    if (!active || done.current) { setN(text.length); return; }
    setN(0); done.current = true;
    const t = setInterval(() => {
      setN(prev => {
        if (prev >= text.length) { clearInterval(t); return prev; }
        return prev + 3;
      });
    }, 24);
    return () => clearInterval(t);
  }, [active, text]);
  return (
    <span className="text-slate-300">
      {text.slice(0, n)}
      {n < text.length && <span className="animate-blink text-neon-cyan">▌</span>}
    </span>
  );
}
