"""E5 听风 · VOC 舆情员（PLAN §1/§4）：评论/反馈 → TOP-N 主题 + 占比 + 代表原声 + 建议。

离线为主力：中文关键词字典分桶（物流/包装/客服/质量/价格/体验）；
在线时用 LLM 复核主题命名与改进建议（失败不阻塞）。
禁止删除原始记录（权限约束在员工档案里声明）。
"""
from __future__ import annotations

import re

from .base import AgentCtx, AgentResult, BaseAgent
from .common import _thinking, doc_text, to_jsonable

BUCKETS: list[tuple[str, list[str]]] = [
    ("物流时效", ["物流", "快递", "配送", "发货慢", "到货", "没更新", "运输", "签收", "驿站", "自提", "等了", "才到", "时效"]),
    ("包装破损", ["包装", "破损", "碎了", "裂了", "瘪了", "变形", "漏了", "磕碰", "压坏", "湿透", "缺件", "少发", "发错"]),
    ("客服服务", ["客服", "回复", "态度", "人工", "不回", "没人理", "推诿", "机器人", "排队", "投诉"]),
    ("质量做工", ["质量", "材质", "做工", "瑕疵", "毛刺", "异味", "掉漆", "生锈", "噪音", "不结实", "耐用"]),
    ("价格性价比", ["太贵", "价格", "性价比", "便宜", "优惠", "活动价", "差价", "退货", "退款"]),
]


def _rows_of(text: str, filename: str) -> list[str]:
    low = filename.lower()
    lines = [ln.strip() for ln in (text or "").splitlines() if ln.strip()]
    if not lines:
        return []
    first = lines[0]
    is_csv = low.endswith(".csv") or ("," in first and "，" not in first)
    if is_csv:
        headerish = any(k in first.lower() for k in ("review", "评论", "评价", "content", "score", "rating"))
        data = lines[1:] if headerish else lines
        out = []
        for ln in data:
            parts = [p.strip().strip('"') for p in ln.split(",")]
            out.append(max(parts, key=len))
        return [x for x in out if x]
    return lines


class VocAgent(BaseAgent):
    code = "E5"

    async def plan_hint(self, p: dict) -> bool:
        if p.get("kind") != "file":
            return False
        if p.get("file_kind") == "csv" and any(k in (p.get("filename") or "").lower() for k in ("review", "评论")):
            return True
        return p.get("file_kind") == "txt" and any(k in (p.get("filename") or "").lower() for k in ("review", "评论", "voc"))

    async def execute(self, ctx: AgentCtx) -> AgentResult:
        doc_id = (ctx.payload or {}).get("doc_id")
        if not doc_id:
            raise RuntimeError("听风需要 file 任务（doc_id: 评论 csv/txt）")

        _thinking(ctx, "读取评论数据，逐条扫描关键词信号…")
        text, filename = await doc_text(doc_id)
        rows = _rows_of(text, filename)
        total = len(rows)
        if total == 0:
            return AgentResult(output={"total_reviews": 0, "topics": [], "advice": ["文件里没有可解析的评论行"]},
                               reasoning="[离线模式] 评论为空，如实返回")
        _thinking(ctx, f"有效评论 {total} 条，分 5 个主题桶计数…")

        counts: dict[str, int] = {}
        quotes: dict[str, list[str]] = {name: [] for name, _ in BUCKETS}
        for r in rows:
            hit_names = [name for name, kws in BUCKETS if any(k in r for k in kws)]
            for name in set(hit_names):
                counts[name] = counts.get(name, 0) + 1
                if len(quotes[name]) < 3 and 6 <= len(r) <= 60:
                    quotes[name].append(r)

        topics = []
        for name, _ in BUCKETS:
            c = counts.get(name, 0)
            if c > 0:
                topics.append({"name": name, "count": c, "ratio": round(c / total, 3),
                               "examples": quotes[name][:3]})
        topics.sort(key=lambda t: t["count"], reverse=True)
        top_n = topics[:4]

        _thinking(ctx, "汇总 TOP-N 占比与代表原声，生成改进建议…")
        advice = self._offline_advice(top_n, total)
        offline = True
        try:
            advice = await self._polish_advice(ctx, top_n, advice)
            offline = False
        except Exception:
            offline = True

        out = to_jsonable({
            "total_reviews": total,
            "topics": top_n,
            "advice": advice,
            "source": filename,
        })
        reasoning = (f"解析 {total} 条评论 → 5 桶关键词分桶 → TOP{len(top_n)}："
                     + "、".join(f"{t['name']} {t['ratio']:.0%}" for t in top_n)
                     + ("" if not offline else "；[离线模式] 建议为规则模板") )
        return AgentResult(output=out, reasoning=reasoning)

    # ---------------- 内部 ----------------

    def _offline_advice(self, top_n: list[dict], total: int) -> list[str]:
        map_ = {
            "物流时效": "与承运商谈时效 SLA 或切换仓配区域，发货页明示预计到达",
            "包装破损": "易损部位加缓冲/卡扣工序，出库抽检拍照留档",
            "客服服务": "高峰时段增派人力，常见售后问题配置快捷话术与自动补偿路径",
            "质量做工": "拉出差评批次做来料与制程追溯，连续两批复现则停线整改",
            "价格性价比": "核对竞品价差，用赠品/分期替代直接降价保住毛利",
        }
        adv = [f"「{t['name']}」提及占比 {t['ratio']:.0%}（{t['count']}/{total}）：{map_.get(t['name'], '建议专项跟进')}"
               for t in top_n]
        neg = sum(1 for t in top_n if t["ratio"] >= 0.1)
        if not neg:
            adv.append("各主题占比均较低，整体口碑平稳，维持现有节奏并持续监控")
        return adv[:5]

    async def _polish_advice(self, ctx: AgentCtx, top_n: list[dict], fallback: list[str]) -> list[str]:
        import json

        system = ("你是电商 VOC 分析师。根据主题占比给出 3-5 条可执行的改进建议（中文，每条<=40字），"
                  "只输出 JSON：{\"advice\":[...]}")
        data_txt = "、".join(f"{t['name']}({t['ratio']:.0%})" for t in top_n)
        t, _, _ = await ctx.llm.chat(system, [{"role": "user", "content": data_txt}], json_mode=True,
                                     employee_id=ctx.employee.get("id") if isinstance(ctx.employee, dict) else None)
        s = (t or "").strip()
        if s.startswith("```"):
            s = s.strip("`").lstrip("json").strip()
        data = json.loads(s)
        adv = [str(x).strip() for x in (data.get("advice") or []) if str(x).strip()]
        if not adv:
            raise ValueError("LLM 未返回有效建议")
        return adv[:5]
