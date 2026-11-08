import type { Employee, Permissions } from "../types";
import { EMP_STATUS, fmtPct, fmtSec } from "../lib/fmt";

export default function Staff({ employees }: { employees: Employee[]; onChanged?: () => void }) {
  if (employees.length === 0) {
    return <div className="panel mx-auto mt-10 max-w-lg px-4 py-8 text-center text-[13px] text-slate-600">正在加载班组…（后端不可用时此处为空）</div>;
  }
  return (
    <div className="mx-auto max-w-[1500px] space-y-4 p-4">
      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
        {employees.map(e => <Card key={e.id} e={e} />)}
      </div>
    </div>
  );
}

function Card({ e }: { e: Employee }) {
  const st = EMP_STATUS[e.status] ?? EMP_STATUS.standby;
  return (
    <div className="panel flex flex-col p-4">
      <div className="mb-2.5 flex items-center gap-3">
        <span className="text-[26px]">{e.emoji}</span>
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2 text-[14px] font-semibold text-slate-100">
            <span className="truncate">{e.name}</span>
            <span className="chip font-mono border-ink-500 bg-ink-800 text-slate-400">{e.code}</span>
          </div>
          <div className="truncate text-[12px] text-slate-500">{e.title}</div>
        </div>
        <div className={`flex items-center gap-1.5 text-[11px] ${st.cls}`}>
          <span className={`inline-block h-1.5 w-1.5 rounded-full ${st.dot}`} />{st.label}
        </div>
      </div>
      <p className="mb-3 line-clamp-3 text-[12px] leading-relaxed text-slate-400">{e.jd}</p>
      <div className="mb-3 space-y-1.5">
        <PermRow label="可自主" tone="emerald" items={e.permissions.autonomous} />
        <PermRow label="需审批" tone="amber" items={e.permissions.approval_required} />
        <PermRow label="禁止" tone="red" items={e.permissions.forbidden} />
      </div>
      <div className="mt-auto grid grid-cols-4 gap-2 border-t border-ink-700 pt-3 text-center">
        <Stat label="今日任务" v={String(e.metrics.tasks_today)} />
        <Stat label="成功率" v={fmtPct(e.metrics.success_rate)} />
        <Stat label="均耗时" v={fmtSec(e.metrics.avg_seconds)} />
        <Stat label="估算成本" v={`¥${e.metrics.cost_est.toFixed(2)}`} />
      </div>
      {e.model && <div className="mt-2 text-right text-[11px] text-slate-600">model: <span className="font-mono">{e.model}</span></div>}
    </div>
  );
}

const TONE: Record<string, string> = {
  emerald: "border-emerald-500/30 bg-emerald-500/5 text-emerald-300/90",
  amber: "border-amber-500/30 bg-amber-500/5 text-amber-300/90",
  red: "border-red-500/30 bg-red-500/5 text-red-300/80",
};

function PermRow({ label, tone, items }: { label: string; tone: string; items: string[] }) {
  if (!items.length) return null;
  return (
    <div className="flex items-start gap-2">
      <span className="w-11 shrink-0 pt-0.5 text-[11px] text-slate-500">{label}</span>
      <div className="flex flex-wrap gap-1">
        {items.map((it, i) => <span key={i} className={`chip ${TONE[tone]}`}>{it}</span>)}
      </div>
    </div>
  );
}

function Stat({ label, v }: { label: string; v: string }) {
  return (
    <div>
      <div className="font-mono text-[13px] text-slate-200">{v}</div>
      <div className="mt-0.5 text-[10px] text-slate-600">{label}</div>
    </div>
  );
}
