"""SUP 调度长·中枢（PLAN §1/§4）：意图识别 → 选派数字员工 → 给出路由理由。

策略：员工 plan_hint 规则打分（快、稳）→ 无命中且在线时 LLM 分类 → 兜底 E2 老查（自由问答）。
M1 只串 1 步（引擎支持多步，UI 发起均为单员工任务）。
"""
from __future__ import annotations

import json

_FALLBACK = "E2"


async def classify(payload: dict, llm=None) -> tuple[str, str]:
    """返回 (employee_code, 路由理由)。"""
    from .analyst import AnalystAgent
    from .copy import CopyAgent
    from .docqa import DocQAAgent
    from .minutes import MinutesAgent
    from .voc import VocAgent

    candidates: list[tuple[str, object]] = []
    for cls in (AnalystAgent, DocQAAgent, MinutesAgent, CopyAgent, VocAgent):
        a = cls()
        try:
            if await a.plan_hint(payload or {}):
                candidates.append((a.code, a))
        except Exception:
            continue

    if len(candidates) == 1:
        return candidates[0][0], f"规则命中：{candidates[0][1].__class__.__name__}"
    if len(candidates) > 1:
        # txt 同时命中 E3(纪要)/E5(评论) 等场景：评论特征优先
        prio = {"E5": 0, "E4": 0, "E1": 1, "E2": 2, "E3": 3}
        code = sorted(candidates, key=lambda c: prio.get(c[0], 9))[0][0]
        return code, f"多重规则命中，按岗位优先级选 {code}"

    # 无规则命中：自由文本
    text = str((payload or {}).get("text") or "")
    if llm is not None and getattr(llm, "online", False):
        try:
            return await _llm_classify(llm, payload)
        except Exception:
            pass
    if text:
        return _FALLBACK, "[离线模式] 自由文本无规则命中，默认派发文档问答官"
    return _FALLBACK, "未知任务形态，兜底路由到文档问答官"


async def _llm_classify(llm, payload: dict) -> tuple[str, str]:
    system = ("你是数字班组的调度长。把任务派给最合适的员工，代号：\n"
              "E1 阿数(报表分析, xlsx/csv 数据报表) / E2 老查(制度文档问答) / "
              "E3 小纪(会议纪要+行动项) / E4 美句(文案改写) / E5 听风(评论舆情分析)。\n"
              "只输出 JSON：{\"code\":\"E?\",\"reason\":\"...\"}")
    brief = json.dumps(payload, ensure_ascii=False)[:800]
    t, _, _ = await llm.chat(system, [{"role": "user", "content": brief}], json_mode=True)
    s = (t or "").strip()
    if s.startswith("```"):
        s = s.strip("`").lstrip("json").strip()
    data = json.loads(s) if "{" in s else json.loads(s[s.find("{"): s.rfind("}") + 1])
    code = str(data.get("code", "")).upper()
    if code not in {"E1", "E2", "E3", "E4", "E5"}:
        raise ValueError("LLM 路由结果非法")
    return code, "LLM 意图识别：" + str(data.get("reason", ""))[:60]


class SupervisorInfo:
    code = "SUP"

    @staticmethod
    async def plan_hint(p: dict) -> bool:
        return False

    @staticmethod
    async def execute(ctx):  # pragma: no cover - SUP 不作为执行步
        raise RuntimeError("调度长不执行任务步，路由在 POST /api/tasks 中完成")
