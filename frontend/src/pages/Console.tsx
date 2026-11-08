import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "../lib/api";
import Chart from "../components/Chart";
import { fmtPct, fmtSec } from "../lib/fmt";
import type { DocumentInfo, UsageSummary } from "../types";

export default function ConsolePage() {
  const [usage, setUsage] = useState<UsageSummary | null>(null);
  const [docs, setDocs] = useState<DocumentInfo[]>([]);
  const [days, setDays] = useState(7);
  const [uploaded, setUploaded] = useState<string | null>(null);

  const refreshUsage = useCallback(async () => {
    const r = await api.usage(days);
    if (r.ok && r.data) setUsage(r.data);
  }, [days]);
  const refreshDocs = useCallback(async () => {
    const r = await api.documents();
    if (r.ok && r.data) setDocs(r.data.documents);
  }, []);

  useEffect(() => { refreshUsage(); }, [refreshUsage]);
  useEffect(() => {
    refreshDocs();
    const t = setInterval(refreshDocs, 5000);
    return () => clearInterval(t);
  }, [refreshDocs]);

  const trendOpt = usage ? {
    title: { text: `近 ${days} 天 Token / 调用趋势`, textStyle: { fontSize: 12, color: "#94a3b8" } },
    tooltip: { trigger: "axis" },
    legend: { data: ["tokens", "调用次数"], top: 0, right: 0, textStyle: { color: "#64748b", fontSize: 11 } },
    xAxis: { type: "category", data: usage.trend.map(t => t.date.slice(5)), axisLabel: { color: "#64748b" } },
    yAxis: [{ type: "value", axisLabel: { color: "#64748b" } }],
    series: [
      { name: "tokens", type: "line", smooth: true, data: usage.trend.map(t => t.tokens), itemStyle: { color: "#22d3ee" }, areaStyle: { color: "rgba(34,211,238,.08)" } },
      { name: "调用次数", type: "bar", data: usage.trend.map(t => t.calls), itemStyle: { color: "rgba(167,139,250,.55)" } },
    ],
  } : null;

  return (
    <div className="mx-auto max-w-[1500px] space-y-4 p-4">
      {/* 总览 */}
      {usage && (
        <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
          <Big label={`近 ${days} 天调用`} v={String(usage.totals.calls)} />
          <Big label="输入 Tokens" v={usage.totals.tokens_in.toLocaleString()} />
          <Big label="输出 Tokens" v={usage.totals.tokens_out.toLocaleString()} />
          <Big label="估算成本" v={`¥ ${usage.totals.cost_est.toFixed(2)}`} accent />
        </div>
      )}

      <div className="grid gap-4 xl:grid-cols-2">
        {/* 趋势 */}
        <div className="panel p-3">
          <div className="mb-2 flex items-center justify-between px-1">
            <span className="text-[13px] font-medium text-slate-300">用量趋势</span>
            <div className="flex gap-1">
              {[7, 14].map(n => (
                <button key={n} onClick={() => setDays(n)}
                  className={`chip cursor-pointer ${days === n ? "border-cyan-500/50 bg-cyan-500/10 text-cyan-300" : "border-ink-500 bg-ink-800 text-slate-500"}`}>
                  近{n}天
                </button>
              ))}
            </div>
          </div>
          {trendOpt ? <Chart option={trendOpt} height={240} />
            : <div className="py-16 text-center text-[13px] text-slate-600">暂无用量数据</div>}
        </div>

        {/* 员工用量表 */}
        <div className="panel overflow-x-auto p-3">
          <div className="mb-2 px-1 text-[13px] font-medium text-slate-300">员工用量（近 {days} 天）</div>
          {!usage || usage.per_employee.length === 0
            ? <div className="py-12 text-center text-[13px] text-slate-600">暂无数据</div>
            : (
              <table className="w-full text-left text-[12px]">
                <thead>
                  <tr className="border-b border-ink-600 text-[11px] uppercase tracking-wider text-slate-500">
                    <th className="py-1.5 font-medium">员工</th><th className="py-1.5 font-medium">任务</th>
                    <th className="py-1.5 font-medium">成功率</th><th className="py-1.5 font-medium">均耗时</th>
                    <th className="py-1.5 text-right font-medium">Tokens(入/出)</th><th className="py-1.5 text-right font-medium">成本</th>
                  </tr>
                </thead>
                <tbody>
                  {usage.per_employee.map(p => (
                    <tr key={p.code} className="border-b border-ink-700/60">
                      <td className="py-2 text-slate-200">{p.emoji} {p.name} <span className="font-mono text-[10px] text-slate-600">{p.code}</span></td>
                      <td className="py-2 font-mono text-slate-300">{p.tasks}</td>
                      <td className="py-2 font-mono text-slate-300">{fmtPct(p.success_rate)}</td>
                      <td className="py-2 font-mono text-slate-300">{fmtSec(p.avg_seconds)}</td>
                      <td className="py-2 text-right font-mono text-slate-400">{p.tokens_in.toLocaleString()} / {p.tokens_out.toLocaleString()}</td>
                      <td className="py-2 text-right font-mono text-amber-300/90">¥{p.cost_est.toFixed(2)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
        </div>
      </div>

      {/* 知识底座 */}
      <DocLibrary docs={docs} onChanged={refreshDocs} uploaded={uploaded} onUploaded={setUploaded} />
    </div>
  );
}

function Big({ label, v, accent }: { label: string; v: string; accent?: boolean }) {
  return (
    <div className="panel px-4 py-3">
      <div className={`font-mono text-[20px] ${accent ? "text-amber-300" : "text-slate-100"}`}>{v}</div>
      <div className="mt-1 text-[11px] text-slate-500">{label}</div>
    </div>
  );
}

function DocLibrary({ docs, onChanged, uploaded, onUploaded }: {
  docs: DocumentInfo[]; onChanged: () => void; uploaded: string | null; onUploaded: (s: string | null) => void;
}) {
  const fileRef = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState(false);

  const onFile = async (f: File) => {
    setBusy(true);
    const r = await api.uploadDocument(f);
    setBusy(false);
    onUploaded(r.ok ? `《${f.name}》已入库并开始索引` : `上传失败：${r.error}`);
    setTimeout(() => onUploaded(null), 4000);
    onChanged();
  };

  return (
    <div className="panel p-3">
      <div className="mb-2 flex items-center justify-between px-1">
        <span className="text-[13px] font-medium text-slate-300">知识底座（语料 / 报表 · RAG 向量库）</span>
        <div className="flex items-center gap-2">
          {uploaded && <span className="text-[11px] text-emerald-300">{uploaded}</span>}
          <input ref={fileRef} type="file" accept=".txt,.md,.csv,.xlsx,.xls" className="hidden"
            onChange={e => { const f = e.target.files?.[0]; if (f) onFile(f); e.currentTarget.value = ""; }} />
          <button disabled={busy} onClick={() => fileRef.current?.click()}
            className="rounded-md border border-cyan-500/50 bg-cyan-500/10 px-3 py-1.5 text-[12px] font-medium text-cyan-300 transition hover:bg-cyan-500/20 disabled:opacity-50">
            {busy ? "上传中…" : "＋ 上传文件"}
          </button>
        </div>
      </div>
      {docs.length === 0
        ? <div className="py-8 text-center text-[13px] text-slate-600">知识库为空 —— 支持 txt / md / csv / xlsx</div>
        : (
          <table className="w-full text-left text-[12px]">
            <thead>
              <tr className="border-b border-ink-600 text-[11px] uppercase tracking-wider text-slate-500">
                <th className="py-1.5 font-medium">文件</th><th className="py-1.5 font-medium">类型</th>
                <th className="py-1.5 text-right font-medium">大小</th><th className="py-1.5 text-right font-medium">行数</th>
                <th className="py-1.5 text-center font-medium">索引</th><th className="py-1.5 font-medium">预览</th>
              </tr>
            </thead>
            <tbody>
              {docs.map(d => (
                <tr key={d.id} className="border-b border-ink-700/60">
                  <td className="py-2 pr-2 font-mono text-slate-200">{d.filename}</td>
                  <td className="py-2 text-slate-500">{d.kind}</td>
                  <td className="py-2 text-right font-mono text-slate-400">{(d.size / 1024).toFixed(1)} KB</td>
                  <td className="py-2 text-right font-mono text-slate-400">{d.rows ?? "—"}</td>
                  <td className="py-2 text-center">{d.indexed
                    ? <span className="chip border-emerald-500/40 bg-emerald-500/10 text-emerald-300">已索引</span>
                    : <span className="chip border-amber-500/40 bg-amber-500/10 text-amber-300">索引中…</span>}</td>
                  <td className="max-w-[320px] truncate py-2 text-slate-500">{d.text_preview}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
    </div>
  );
}
