import type { Step } from "../types";
import Chart from "./Chart";

function InsightCards({ items }: { items: { level: string; text: string }[] }) {
  const tone: Record<string, string> = {
    info: "border-ink-500 bg-ink-800 text-slate-300",
    warning: "border-amber-500/40 bg-amber-500/10 text-amber-200",
    high: "border-red-500/50 bg-red-500/10 text-red-200",
  };
  const icon: Record<string, string> = { info: "ℹ", warning: "⚠", high: "🔴" };
  return (
    <div className="space-y-2">
      {items.map((it, i) => (
        <div key={i} className={`rounded-md border px-3 py-2 text-[13px] leading-relaxed ${tone[it.level] ?? tone.info}`}>
          <span className="mr-1.5">{icon[it.level] ?? "•"}</span>{it.text}
        </div>
      ))}
    </div>
  );
}

function Citations({ items }: { items: { doc_name: string; seq: number; snippet: string }[] }) {
  return (
    <div className="space-y-1.5">
      {items.map((c, i) => (
        <div key={i} className="flex gap-2 rounded-md border border-emerald-500/30 bg-emerald-500/5 px-3 py-2 text-[12px]">
          <span className="chip shrink-0 border-emerald-500/40 text-emerald-300">{c.doc_name} · 第{c.seq}段</span>
          <span className="text-slate-400">{c.snippet}</span>
        </div>
      ))}
    </div>
  );
}

function ActionTable({ items }: { items: { item: string; owner: string; deadline: string }[] }) {
  return (
    <table className="w-full text-left text-[13px]">
      <thead>
        <tr className="border-b border-ink-600 text-[11px] uppercase tracking-wider text-slate-500">
          <th className="py-1.5 pr-3 font-medium">行动项</th><th className="py-1.5 pr-3 font-medium">负责人</th><th className="py-1.5 font-medium">期限</th>
        </tr>
      </thead>
      <tbody>
        {items.map((a, i) => (
          <tr key={i} className="border-b border-ink-700/60">
            <td className="py-1.5 pr-3 text-slate-300">{a.item}</td>
            <td className="py-1.5 pr-3"><span className="chip border-violet-500/40 bg-violet-500/10 text-violet-300">@{a.owner}</span></td>
            <td className="py-1.5 text-amber-300/90">{a.deadline}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function VocTopics({ topics, advice, total }: { topics: { name: string; ratio: number; examples: string[] }[]; advice: string[]; total: number | null }) {
  return (
    <div className="space-y-3">
      {total != null && <div className="text-[12px] text-slate-500">共分析 {total} 条评论</div>}
      {topics.map((t, i) => (
        <div key={i} className="rounded-md border border-ink-600 bg-ink-800 p-3">
          <div className="mb-2 flex items-center gap-2 text-[13px]">
            <span className="font-medium text-slate-200">TOP{i + 1} · {t.name}</span>
            <div className="h-1.5 flex-1 overflow-hidden rounded bg-ink-600">
              <div className="h-full rounded bg-gradient-to-r from-cyan-500 to-violet-500" style={{ width: `${Math.round(t.ratio * 100)}%` }} />
            </div>
            <span className="font-mono text-[12px] text-neon-cyan">{Math.round(t.ratio * 100)}%</span>
          </div>
          <div className="space-y-1">
            {t.examples.map((e, j) => (
              <div key={j} className="text-[12px] italic text-slate-500">“{e}”</div>
            ))}
          </div>
        </div>
      ))}
      {advice.length > 0 && (
        <div className="rounded-md border border-amber-500/30 bg-amber-500/5 px-3 py-2 text-[12px] text-amber-200/90">
          {advice.map((a, i) => <div key={i}>· {a}</div>)}
        </div>
      )}
    </div>
  );
}

function CopyDiff({ original, optimized, changes }: { original: string; optimized: string; changes: string[] }) {
  return (
    <div className="grid gap-2 md:grid-cols-2">
      <div className="rounded-md border border-red-500/25 bg-red-500/5 p-3 text-[13px] text-slate-400">
        <div className="mb-1 text-[11px] uppercase tracking-wider text-red-300/70">优化前</div>{original}
      </div>
      <div className="rounded-md border border-emerald-500/30 bg-emerald-500/5 p-3 text-[13px] text-slate-200">
        <div className="mb-1 text-[11px] uppercase tracking-wider text-emerald-300/70">优化后</div>{optimized}
      </div>
      {changes.length > 0 && (
        <div className="md:col-span-2 rounded-md border border-ink-600 bg-ink-800 p-3 text-[12px] text-slate-400">
          <div className="mb-1 text-[11px] uppercase tracking-wider text-slate-500">改动说明</div>
          {changes.map((c, i) => <div key={i}>· {c}</div>)}
        </div>
      )}
    </div>
  );
}

function KV({ k, v }: { k: string; v: React.ReactNode }) {
  return <div className="flex justify-between gap-3 border-b border-ink-700/50 py-1 text-[12px]"><span className="text-slate-500">{k}</span><span className="text-right text-slate-300">{v}</span></div>;
}

/** 按员工输出契约渲染 step.output（E1 报表 / E2 问答 / E3 纪要 / E4 文案 / E5 VOC / 审批）。 */
export default function OutputRenderer({ step }: { step: Step }) {
  const o = step.output;
  if (!o || typeof o !== "object") {
    if (o == null) return <div className="text-[12px] text-slate-600">（无输出）</div>;
    return <pre className="whitespace-pre-wrap text-[12px] text-slate-400">{String(o)}</pre>;
  }

  // 审批步
  if (step.type === "approval") {
    const decision = o.decision;
    return (
      <div className="space-y-1">
        {decision && (
          <div className={`chip w-fit ${decision === "approved" ? "border-emerald-500/40 bg-emerald-500/10 text-emerald-300" : "border-red-500/40 bg-red-500/10 text-red-300"}`}>
            {decision === "approved" ? "✓ 已批准" : "✗ 已拒绝"}
          </div>
        )}
        {!decision && <div className="chip w-fit border-amber-500/40 bg-amber-500/10 text-amber-300">等待人工决策</div>}
        {o.note && <div className="text-[12px] text-slate-500">备注：{o.note}</div>}
      </div>
    );
  }

  const parts: React.ReactNode[] = [];
  if (Array.isArray(o.insights)) parts.push(<InsightCards key="in" items={o.insights} />);
  if (Array.isArray(o.risks)) parts.push(<InsightCards key="ri" items={o.risks.map((r: any) => ({ level: r.level ?? "high", text: `风险 · ${r.text}` }))} />);
  if (o.chart) parts.push(<div key="ch" className="rounded-md border border-ink-600 bg-ink-900/60 p-2"><Chart option={o.chart} height={300} /></div>);
  if (typeof o.answer === "string") parts.push(
    <div key="an" className="space-y-2">
      <div className="whitespace-pre-wrap text-[13px] leading-relaxed text-slate-200">{o.answer}</div>
      {Array.isArray(o.citations) && <Citations items={o.citations} />}
    </div>);
  if (typeof o.summary === "string") parts.push(
    <div key="su" className="space-y-2">
      <div className="whitespace-pre-wrap rounded-md border border-ink-600 bg-ink-800 p-3 text-[13px] leading-relaxed text-slate-300">{o.summary}</div>
      {Array.isArray(o.topics) && o.topics.every((t: any) => typeof t === "string") && (
        <div className="flex flex-wrap gap-1.5">{o.topics.map((t: string, i: number) => <span key={i} className="chip border-ink-500 bg-ink-800 text-slate-400">{t}</span>)}</div>
      )}
      {Array.isArray(o.action_items) && <ActionTable items={o.action_items} />}
    </div>);
  if (typeof o.original === "string" && typeof o.optimized === "string") {
    parts.push(<CopyDiff key="cp" original={o.original} optimized={o.optimized} changes={Array.isArray(o.changes) ? o.changes : []} />);
  }
  if (Array.isArray(o.topics) && o.topics.some((t: any) => t && typeof t === "object" && "ratio" in t)) {
    parts.push(<VocTopics key="vo" topics={o.topics} advice={Array.isArray(o.advice) ? o.advice : []} total={typeof o.total_reviews === "number" ? o.total_reviews : null} />);
  }

  if (parts.length === 0) {
    return (
      <div className="space-y-0.5">
        {Object.entries(o).filter(([k]) => k !== "send_external").map(([k, v]) => (
          <KV key={k} k={k} v={typeof v === "string" ? v : <span className="font-mono">{JSON.stringify(v).slice(0, 120)}</span>} />
        ))}
      </div>
    );
  }
  return <div className="space-y-3">{parts}</div>;
}
