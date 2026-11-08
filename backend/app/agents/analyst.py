"""E1 阿数 · 报表分析师（PLAN §1/§4）：xlsx/csv 报表 → 洞察 + ECharts 图 + 风险提示。

在线：pandas 全量统计（规则算数永远做），LLM 仅用于润色洞察措辞（失败即回退模板）。
离线：纯模板洞察。检测到高危异常（ACOS 突变）→ needs_approval：对外发送警示报告。
"""
from __future__ import annotations

from .base import AgentCtx, AgentResult, BaseAgent
from .common import _pick, _thinking, doc_dataframe, to_jsonable

REVIEW_KW = ("review", "评论", "评价")


class AnalystAgent(BaseAgent):
    code = "E1"

    async def plan_hint(self, p: dict) -> bool:
        if p.get("kind") != "file":
            return False
        fk = p.get("file_kind")
        name = (p.get("filename") or "").lower()
        if fk == "xlsx":
            return True
        if fk == "csv":
            return not any(k in name for k in REVIEW_KW)
        return False

    # ---------------- 执行 ----------------

    async def execute(self, ctx: AgentCtx) -> AgentResult:
        doc_id = (ctx.payload or {}).get("doc_id")
        if not doc_id:
            raise RuntimeError("阿数需要 file 任务（doc_id）才能分析报表")

        _thinking(ctx, "读取报表，识别 日期/花费/GMV/转化 列…")
        df = await doc_dataframe(doc_id)
        _thinking(ctx, f"载入 {len(df)} 行 × {len(df.columns)} 列，开始逐日统计…")

        col_date = _pick(df, "日期", "date", "day")
        col_campaign = _pick(df, "campaign", "推广计划", "计划", "渠道", "channel")
        col_cost = _pick(df, "花费", "cost", "spend")
        col_gmv = _pick(df, "gmv", "销售额", "成交", "sales", "revenue")

        if col_cost is None or col_gmv is None:
            return await self._generic(ctx, df)

        df[col_cost] = pd_numeric(df[col_cost])
        df[col_gmv] = pd_numeric(df[col_gmv])
        df["_acos"] = (df[col_cost] / df[col_gmv].replace(0, float("nan")) * 100).round(2)

        total_cost = float(df[col_cost].sum())
        total_gmv = float(df[col_gmv].sum())
        acos_total = round(total_cost / total_gmv * 100, 1) if total_gmv else None

        _thinking(ctx, f"累计花费 ¥{_fmt_money(total_cost)}，GMV ¥{_fmt_money(total_gmv)}，"
                       f"综合 ACOS {_pct(acos_total)}")

        insights: list[dict] = []
        risks: list[dict] = []
        insights.append({"level": "info", "text":
                         f"近 {len(df)} 行数据累计花费 ¥{_fmt_money(total_cost)}，GMV ¥{_fmt_money(total_gmv)}，"
                         f"综合 ACOS {_pct(acos_total)}"})

        # ---- 逐日异常检出（spike > 1.6×基线中位数）----
        series: list[tuple[str, float, float]] = []
        if col_date is not None:
            try:
                d = df.copy()
                d["_d"] = _fmt_date(d[col_date])
                daily = (d.groupby("_d", as_index=False)
                         .agg(cost=(col_cost, "sum"), gmv=(col_gmv, "sum")))
                daily["_acos"] = (daily["cost"] / daily["gmv"].replace(0, float("nan")) * 100).round(1)
                series = []
                for t in daily.itertuples(index=False):
                    day, cost, gmv, a = t[0], float(t[1]), float(t[2]), (float(t[3]) if t[3] == t[3] else 0.0)
                    series.append((str(day)[:10], cost, a))
            except Exception:
                series = []

        spikes, spike_days = [], []
        base = 0.0
        if series:
            valid = [a for _, _, a in series if a > 0]
            if valid:
                base = float(sorted(valid)[len(valid) // 2])
                for i, (day, cost, a) in enumerate(series):
                    if a > 1.6 * base:
                        spikes.append(i)
                        spike_days.append(day)
        if spikes:
            spike_acos = [series[i][2] for i in spikes]
            lo = min(a for a in spike_acos if a > 0) or 0.0
            hi = max(spike_acos)
            seg = f"{spike_days[0]} 至 {spike_days[-1]}" if len(set(spike_days)) > 1 else spike_days[0]
            insights.append({"level": "warning", "text":
                             f"{seg} 连续 {len(spikes)} 天日 ACOS 飙升至 {lo:.0f}%-{hi:.0f}%"
                             f"（基线约 {base:.0f}%）：花费显著放大而 GMV 增长滞后，"
                             f"疑似出价/竞价加剧或转化率下滑"})
            risks.append({"level": "high", "text":
                          f"异常区间 {seg} 日 ACOS 峰值 {hi:.0f}%，远高于健康线 30%：建议立即下调出价/收窄人群定向，48h 内未回落则暂停投放"})
            _thinking(ctx, f"检出异常：{len(spikes)} 天 ACOS 超基线 1.6 倍（峰值 {hi:.0f}%）")
        else:
            _thinking(ctx, "逐日扫描未见显著突变")

        # ---- campaign 维度 ----
        if col_campaign is not None and df[col_campaign].nunique() > 1:
            camp = (df.groupby(col_campaign, as_index=False)
                    .agg(cost=(col_cost, "sum"), gmv=(col_gmv, "sum")))
            camp["_acos"] = (camp["cost"] / camp["gmv"].replace(0, float("nan")) * 100).round(1)
            camps = []
            for t in camp.itertuples(index=False):
                a = float(t[3]) if t[3] == t[3] else 0.0
                camps.append((str(t[0]), float(t[1]), a))
            camps.sort(key=lambda x: x[2], reverse=True)
            worst, best = camps[0], camps[-1]
            if worst[2] and acos_total and worst[2] > 1.5 * acos_total:
                risks.append({"level": "medium", "text":
                              f"campaign『{worst[0]}』综合 ACOS {worst[2]:.0f}%，明显高于整体（{acos_total:.0f}%），建议降预算 20-30% 或降价观察"})
            if best[2] and acos_total and best[2] < 0.75 * acos_total:
                insights.append({"level": "info", "text":
                                 f"campaign『{best[0]}』ACOS 仅 {best[2]:.0f}%，为全表最低，存在加预算空间"})
            _thinking(ctx, f"campaign 对比：最差『{worst[0]}』{worst[2]:.0f}% / 最优『{best[0]}』{best[2]:.0f}%")

        # ---- campaign 级时序突变（某 campaign 出现连续 ≥2 天 ACOS 超自身中位数 1.5 倍的区段）----
        camp_spike = None
        if col_campaign is not None and col_date is not None and df[col_campaign].nunique() > 1:
            try:
                dd = d.copy()
                cd = (dd.groupby([col_campaign, "_d"], as_index=False)
                      .agg(cost=(col_cost, "sum"), gmv=(col_gmv, "sum")))
                cd["_a"] = cd["cost"] / cd["gmv"].replace(0, float("nan")) * 100
                cd = cd.sort_values("_d")
                best_key = (0.0, 0)
                for name, g in cd.groupby(col_campaign):
                    pairs = [(str(rw["_d"])[:10], float(rw["_a"])) for rw in g.to_dict("records") if rw["_a"] == rw["_a"] and rw["_a"] > 0]
                    if len(pairs) < 6:
                        continue
                    vals = [a for _, a in pairs]
                    med = float(sorted(vals)[max(1, len(vals) // 4)])  # 下四分位做基线，避免异常段污染中位数
                    if med <= 0:
                        continue
                    # 找最长连续超标段
                    def _consider(run):
                        nonlocal best_key, camp_spike
                        if len(run) < 2:
                            return
                        seg_med = float(sorted(x for _, x in run)[len(run) // 2])
                        key = (len(run), seg_med / med)  # 优先更长异常段，其次幅度
                        if key > best_key:
                            best_key = key
                            camp_spike = (str(name), round(med, 1), round(seg_med, 1), run[0][0], run[-1][0], len(run))

                    run = []
                    for day, a in pairs:
                        if a > 1.5 * med:
                            run.append((day, a))
                        else:
                            _consider(run)
                            run = []
                    _consider(run)
            except Exception:
                camp_spike = None
            # 备注：ratio 相同时优先更长异常段（上面比较已含长度加权）
        if camp_spike:
            name, med, seg_med, d1, d2, n = camp_spike
            seg = f"{d1} 至 {d2}" if d1 != d2 else d1
            insights.append({"level": "warning", "text":
                             f"campaign『{name}』在 {seg} 连续 {n} 天 ACOS 抬升至 {seg_med:.0f}%（自身低位基线 {med:.0f}%，"
                             f"{seg_med / med:.1f} 倍）：GMV 基本持平而花费抬升，这种单 campaign 区段异常在多计划报表里最容易被整体数字稀释"})
            risks.append({"level": "high", "text":
                          f"campaign『{name}』{seg} 日 ACOS 从 {med:.0f}% 抬升至 {seg_med:.0f}%：建议立即下调该计划出价 30% 并收窄人群定向，48h 内未回落则暂停投放"})
            if not spike_days:
                spike_days = [d2]
            _thinking(ctx, f"campaign 级突变：『{name}』{seg} {med:.0f}% → {seg_med:.0f}%")

        # ---- 图表（ECharts option）----
        if series:
            chart = {
                "title": {"text": f"日花费 vs ACOS（近{len(series)}天）"},
                "tooltip": {"trigger": "axis"},
                "legend": {"data": ["花费(¥)", "ACOS(%)"]},
                "xAxis": {"type": "category", "data": [d for d, _, _ in series]},
                "yAxis": [{"type": "value", "name": "花费(¥)"},
                          {"type": "value", "name": "ACOS(%)"}],
                "series": [
                    {"name": "花费(¥)", "type": "bar",
                     "data": [round(c, 2) for _, c, _ in series]},
                    {"name": "ACOS(%)", "type": "line", "yAxisIndex": 1,
                     "data": [a for _, _, a in series],
                     "markPoint": {"data": [{"coord": [spike_days[len(spike_days) // 2],
                                                       max(a for _, _, a in series)], "value": "异常"}]}
                     if spikes else {}},
                ],
            }
        else:
            nums = [c for c in df.columns if c not in (col_campaign, col_date)
                    and pd_numeric(df[c]).dtype.kind in "fi" and df[c].notna().sum() > 3]
            chart = {
                "title": {"text": f"报表数值列概览（{len(df)} 行）"},
                "tooltip": {"trigger": "axis"},
                "legend": {"data": [str(c) for c in nums[:4]]},
                "xAxis": {"type": "category", "data": [f"行{i}" for i in range(min(len(df), 60))]},
                "yAxis": {"type": "value"},
                "series": [{"name": str(c), "type": "line",
                            "data": [round(float(v), 2) for v in pd_numeric(df[c]).head(60).fillna(0)]}
                           for c in nums[:4]],
            }

        # ---- LLM 润色（在线增强，可失败）----
        reasoning_base = (f"读取 {len(df)} 行报表 → 识别 日期/花费/GMV{'/' + str(col_campaign) if col_campaign else ''} 列 "
                          f"→ 逐日 ACOS 基线中位数 {base:.0f}% "
                          f"→ {'检出 ' + str(len(spikes)) + ' 天突变' if spikes else '未见突变'} "
                          f"→ 生成 {len(insights)} 条洞察 + 双轴图 + {len(risks)} 条风险")
        offline = False
        try:
            polished = await self._polish(ctx, insights, risks)
            if polished:
                insights = polished
        except Exception:
            offline = True
        if offline:
            reasoning_base = "[离线模式] " + reasoning_base + "（无 LLM，洞察为规则模板）"

        send_external = any(r["level"] == "high" for r in risks)
        out = to_jsonable({
            "insights": insights[:5],
            "chart": chart,
            "risks": risks,
            "totals": {"cost": round(total_cost, 2), "gmv": round(total_gmv, 2),
                       "acos_pct": acos_total, "rows": len(df)},
            "anomaly": bool(spikes) or camp_spike is not None,
            "spike_days": spike_days,
            "send_external": send_external,
        })
        return AgentResult(
            output=out,
            reasoning=reasoning_base,
            needs_approval=send_external,
            approval_payload=(
                {"risk_note": "阿数要把异常警示报告对外发送给管理层（对外发送属审批级动作）",
                 "payload": {"action": "send_external", "recipient": "管理层邮件组",
                             "summary": next((r["text"] for r in risks if r["level"] == "high"),
                                             insights[0]["text"] if insights else "报表异常警示"),
                             "evidence": {"spike_days": spike_days, "chart_title": chart["title"]["text"]}}}
                if send_external else None),
        )

    async def _polish(self, ctx: AgentCtx, insights: list[dict], risks: list[dict]) -> list[dict]:
        """在线：让 LLM 用业务语言重写洞察文本（结构不变）。失败抛出让上层走模板。"""
        import json as _json

        system = ("你是电商投放数据分析师。把给出的洞察条目改写成更专业的中文表述，"
                  "保持每条的 level 不变，保留所有数字，条数不变。"
                  "只输出 JSON：{\"insights\":[{\"level\":..,\"text\":..}]}。")
        text, _, _ = await ctx.llm.chat(
            system,
            [{"role": "user", "content": "待润色的洞察（JSON）：\n" + json_dumps(insights) +
                            "\n风险条目：\n" + json_dumps(risks)}],
            json_mode=True, employee_id=emp_id(ctx))
        data = _loads_json(text)
        got = data.get("insights") if isinstance(data, dict) else None
        if not isinstance(got, list) or not got:
            raise ValueError("LLM 未返回有效 insights")
        merged = []
        for i, item in enumerate(got):
            if not isinstance(item, dict) or not str(item.get("text", "")).strip():
                continue
            merged.append({"level": item.get("level") or (insights[i]["level"] if i < len(insights) else "info"),
                           "text": str(item["text"]).strip()})
        if not merged:
            raise ValueError("LLM insights 全部无效")
        return merged

    async def _generic(self, ctx: AgentCtx, df) -> AgentResult:
        nums = [c for c in df.columns if pd_numeric(df[c]).dtype.kind in "fi"]
        stat_lines = [f"{c}: 均值 {float(pd_numeric(df[c]).mean()):.2f}" for c in nums[:5]]
        out = to_jsonable({
            "insights": [{"level": "info", "text":
                          f"报表共 {len(df)} 行 × {len(df.columns)} 列；未识别出标准花费/GMV 列，按数值列概况：{"，".join(stat_lines) or '无数值列'}"}],
            "chart": {"title": {"text": "数值列概览"}, "xAxis": {"type": "category",
                                                                "data": [f"行{i}" for i in range(min(len(df), 40))]},
                      "yAxis": {"type": "value"},
                      "series": [{"name": str(c), "type": "line",
                                  "data": [round(float(v), 2) for v in pd_numeric(df[c]).head(40).fillna(0)]}
                                 for c in nums[:4]]},
            "risks": [], "totals": {"rows": len(df)}, "anomaly": False, "spike_days": [],
            "send_external": False,
        })
        return AgentResult(output=out,
                           reasoning="[离线模式] 未识别到 花费/GMV 列，退化为数值列概况（无 LLM）")


# ---------------- 小工具 ----------------

def pd_numeric(s):
    import pandas as pd

    return pd.to_numeric(s, errors="coerce")


def _fmt_money(x: float) -> str:
    if x >= 10000:
        return f"{x / 10000:.1f}万"
    return f"{x:,.0f}"


def _pct(x) -> str:
    return f"{x:.1f}%" if x is not None else "—"


def _fmt_date(v):
    import pandas as pd

    if isinstance(v, pd.Series):
        try:
            return pd.to_datetime(v, errors="coerce").dt.strftime("%m-%d")
        except Exception:
            return v.map(lambda x: str(x)[:10])
    try:
        return pd.to_datetime(v).strftime("%m-%d")
    except Exception:
        return str(v)[:10]


def emp_id(ctx: AgentCtx) -> str | None:
    return ctx.employee.get("id") if isinstance(ctx.employee, dict) else None


def json_dumps(obj) -> str:
    import json

    return json.dumps(obj, ensure_ascii=False)


def _loads_json(text: str):
    import json

    t = (text or "").strip()
    if t.startswith("```"):
        t = t.strip("`").lstrip("json").strip()
    try:
        return json.loads(t)
    except Exception:
        i, j = t.find("{"), t.rfind("}")
        if 0 <= i < j:
            return json.loads(t[i:j + 1])
        raise
