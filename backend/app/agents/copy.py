"""E4 美句 · 文案优化师（PLAN §1/§4）：Listing/营销文案改写 → 优化稿 + 改动说明。

在线：LLM 按"卖点前置 + 参数具象 + 信任钩子"改写（json_mode）。
离线：规则重构——拆句成卖点要点、【钩子】前置结构、附一份"待补充参数"清单（诚实告知未联网生成）。
"""
from __future__ import annotations

import json
import re

from .base import AgentCtx, AgentResult, BaseAgent
from .common import _thinking

_GENERIC_WORDS = ("好用", "不错", "推荐", "很好", "喜欢", "满意", "值得", "划算")


class CopyAgent(BaseAgent):
    code = "E4"

    _COPY_SIGNALS = ("文案", "改写", "润色", "广告语", "详情页", "种草", "说服力", "更有吸引力")
    _COPY_TARGETS = ("商品", "产品", "宝贝", "店铺", "链接", "描述", "标题", "文案")

    async def plan_hint(self, p: dict) -> bool:
        if p.get("kind") != "text":
            return False
        if p.get("copy"):
            return True
        text = str(p.get("text") or "")
        return any(w in text for w in self._COPY_SIGNALS) and any(t in text for t in self._COPY_TARGETS)

    async def execute(self, ctx: AgentCtx) -> AgentResult:
        text = str((ctx.payload or {}).get("text") or "").strip()
        if not text:
            raise RuntimeError("美句需要 text 文案内容")
        _thinking(ctx, f"读文案 {len(text)} 字，识别卖点信号词…")

        offline = False
        try:
            optimized, changes = await self._ask_llm(ctx, text)
        except Exception:
            offline = True
            optimized, changes = self._offline_rewrite(text)

        out = {
            "original": text,
            "optimized": optimized,
            "changes": changes,
        }
        reasoning = ("拆解卖点 → "
                     + ("LLM 按 卖点前置/参数具象/信任钩子 改写" if not offline else
                        "[离线模式] 无 LLM：拆句要点化 + 结构重组，参数类表述需人工补齐")
                     + f" → 输出优化稿 + {len(changes)} 条改动说明")
        return AgentResult(output=out, reasoning=reasoning)

    # ---------------- 内部 ----------------

    async def _ask_llm(self, ctx: AgentCtx, text: str) -> tuple[str, list[str]]:
        system = ("你是电商 Listing 文案优化师。改写原则：\n"
                  "1) 卖点前置，首句给最强钩子（质保/时效/参数）；\n"
                  "2) 把空泛形容词换成可核验的参数（若原文没有参数，用【待补充：材质/规格】占位，不得编造）；\n"
                  "3) 增加信任要素（售后承诺/销量/认证，同样不得编造具体数字）；\n"
                  "4) 保留原文所有合规表述。\n"
                  "只输出 JSON：{\"optimized\": \"...\", \"changes\": [\"...\"]}，changes 3-5 条，每条说明改了什么、为什么。")
        t, _, _ = await ctx.llm.chat(system, [{"role": "user", "content": text}], json_mode=True,
                                     employee_id=ctx.employee.get("id") if isinstance(ctx.employee, dict) else None)
        s = (t or "").strip()
        if s.startswith("```"):
            s = s.strip("`").lstrip("json").strip()
        data = json.loads(s) if "{" in s else json.loads(s[s.find("{"): s.rfind("}") + 1])
        optimized = str(data.get("optimized", "")).strip()
        changes = [str(x).strip() for x in (data.get("changes") or []) if str(x).strip()]
        if not optimized:
            raise ValueError("LLM 未返回优化稿")
        return optimized, changes[:5]

    def _offline_rewrite(self, text: str) -> tuple[str, list[str]]:
        sents = [s.strip() for s in re.split(r"(?<=[。；;!！])", text.replace("\n", " ")) if s.strip()]
        bullets, notes = [], []
        for s in sents:
            s = s.strip("。；;")
            if any(w in s for w in _GENERIC_WORDS) and len(s) < 25:
                notes.append(f"空泛表述『{s}』已要点化，建议补一个可核验参数（尺寸/材质/时长）")
            bullets.append("· " + s)
        optimized = "【核心卖点】\n" + ("\n".join(bullets) if bullets else "· " + text.strip())
        optimized += "\n【售后承诺】如有质保/退换/赔付政策，请在此补一句（如：3 年质保·漏液包赔）"
        changes = notes[:2] or ["按卖点结构重排原文句子"]
        changes.append("离线模板改写：参数与承诺位留了占位，联网模式下 LLM 可直接基于原文补齐")
        return optimized, changes[:5]
