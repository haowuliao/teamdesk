"""E3 小纪 · 纪要秘书（PLAN §1/§4）：会议记录/长文 → 纪要 + 行动项表。

在线：全文交给 LLM 抽 摘要/议题/行动项（json_mode）。
离线：标题当议题；按"行动动词 + 人名 + 期限"模式扫行动项；首段当摘要。
reasoning 标注 [离线模式]。
"""
from __future__ import annotations

import json
import re

from .base import AgentCtx, AgentResult, BaseAgent
from .common import _thinking, doc_text, to_jsonable

_ACTION_VERBS = ("完成", "输出", "撰写", "更新", "提交", "跟进", "对接", "确认", "评审", "上线", "发布", "采购", "排查", "修复", "整理", "输出")
_DEADLINE_RE = re.compile(r"(本周[一二三四五六日末]|下周[一二三四五六日]|周[一二三四五六日]前?|[0-9一二三四五六七八九十]{1,4}月?[0-9]{1,2}[日号]前?|月底前?|月底前?|月底|月底|下月底前|三天内|48小时内|尽快|下周内|本周内)")
_OWNER_RE = re.compile(r"([\u4e00-\u9fa5]{2,4})(负责|牵头|来跟|来做|来写)")


def _lines(text: str) -> list[str]:
    out = []
    for ln in (text or "").splitlines():
        ln = ln.strip().lstrip("-*·• \t")
        if ln:
            out.append(ln)
    return out


def _headings(text: str) -> list[str]:
    hs = []
    for ln in (text or "").splitlines():
        m = re.match(r"^#{1,4}\s+(.+)$", ln.strip())
        if m:
            hs.append(m.group(1).strip())
    return hs


def _first_para(text: str) -> str:
    for ln in _lines(text):
        if ln.startswith(("#", "**", "【")):
            continue
        if re.match(r"^[一二三四五六七八九十]+[、.．]", ln):
            continue
        if re.match(r"^[\u4e00-\u9fa5A-Za-z（）]{1,8}\*{0,2}\s*[:：]", ln):  # “参会：…”这类字段行
            continue
        if len(ln) >= 12:
            return ln[:160]
    return ""


def _table_actions(text: str) -> list[dict]:
    """解析 markdown 四列表格（# | 事项 | 负责人 | 期限）。"""
    acts = []
    for ln in (text or "").splitlines():
        s = ln.strip()
        if not s.startswith("|"):
            continue
        cells = [c.strip() for c in s.strip("|").split("|")]
        if len(cells) != 4 or cells[0] in ("#", "") or set(cells[0]) <= set("-: "):
            continue
        acts.append({"item": cells[1][:80], "owner": cells[2] or "待定",
                     "deadline": cells[3] or "未定"})
    return acts


class MinutesAgent(BaseAgent):
    code = "E3"

    async def plan_hint(self, p: dict) -> bool:
        if p.get("kind") != "file":
            return False
        return p.get("file_kind") in ("md", "txt")

    async def execute(self, ctx: AgentCtx) -> AgentResult:
        doc_id = (ctx.payload or {}).get("doc_id")
        if not doc_id:
            raise RuntimeError("小纪需要 file 任务（doc_id: md/txt）")

        _thinking(ctx, "读取会议记录，切分议题段落…")
        text, filename = await doc_text(doc_id)
        n_lines = len(_lines(text))
        _thinking(ctx, f"正文 {n_lines} 行，开始抽取议题与行动项…")

        offline = False
        try:
            summary, topics, actions = await self._ask_llm(ctx, text)
        except Exception:
            offline = True
            summary, topics, actions = self._offline(text)

        if not summary:
            summary = f"文档《{filename}》要点速览（自动纪要）。"
        out = to_jsonable({
            "summary": summary,
            "topics": topics[:8],
            "action_items": actions[:12],
            "source": filename,
        })
        reasoning = (f"读取《{filename}》 {n_lines} 行 → "
                     + ("LLM 抽取摘要/议题/行动项" if not offline else
                        "[离线模式] 无 LLM：标题→议题，行动动词+负责人+期限正则→行动项，首段→摘要")
                     + f" → 议题 {len(topics)} 项，行动项 {len(actions)} 条")
        return AgentResult(output=out, reasoning=reasoning)

    # ---------------- 内部 ----------------

    async def _ask_llm(self, ctx: AgentCtx, text: str) -> tuple[str, list[str], list[dict]]:
        system = ("你是企业会议纪要秘书。基于用户给出的会议记录抽取：\n"
                  "1) summary: 一段话纪要（80-160字，交代结论与重点）；\n"
                  "2) topics: 讨论过的议题（3-6 个短语）；\n"
                  "3) action_items: 行动项数组，每项 {item: 做什么, owner: 负责人(人名, 不确定填'待定'), deadline: 期限(原文表述, 没有填'未定')}。\n"
                  "只输出 JSON：{\"summary\":\"...\",\"topics\":[],\"action_items\":[{\"item\":..,\"owner\":..,\"deadline\":..}]}")
        t, _, _ = await ctx.llm.chat(system, [{"role": "user", "content": text[:6000]}],
                                     json_mode=True,
                                     employee_id=ctx.employee.get("id") if isinstance(ctx.employee, dict) else None)
        s = (t or "").strip()
        if s.startswith("```"):
            s = s.strip("`").lstrip("json").strip()
        data = json.loads(s) if "{" in s else json.loads(s[s.find("{"): s.rfind("}") + 1])
        summary = str(data.get("summary", "")).strip()
        topics = [str(x).strip() for x in (data.get("topics") or []) if str(x).strip()][:8]
        actions = []
        for it in data.get("action_items") or []:
            if isinstance(it, dict) and str(it.get("item", "")).strip():
                actions.append({"item": str(it["item"]).strip(),
                                "owner": str(it.get("owner", "待定")).strip() or "待定",
                                "deadline": str(it.get("deadline", "未定")).strip() or "未定"})
        return summary, topics, actions

    def _offline(self, text: str) -> tuple[str, list[str], list[dict]]:
        topics = _headings(text)
        seen, uniq = set(), []
        for t in topics:
            if t not in seen and len(t) <= 30:
                seen.add(t)
                uniq.append(t)
        if not uniq:
            uniq = [ln[:24] for ln in _lines(text) if len(ln) >= 10][:3]

        actions = _table_actions(text)
        if not actions:
            for ln in _lines(text):
                if "|" in ln:
                    continue
                if not any(v in ln for v in _ACTION_VERBS):
                    continue
                dl = _DEADLINE_RE.search(ln)
                ow = _OWNER_RE.search(ln)
                owner = ow.group(1) if ow else "待定"
                item = re.sub(r"^\[[ xX]\]\s*", "", ln)
                item = re.sub(r"(由|，?@)?[\u4e00-\u9fa5]{2,4}(负责|牵头|来跟|来做|来写)[，,]?", "", item)
                item = item.strip(" ，,、")
                if len(item) < 8:
                    continue
                actions.append({"item": item[:80], "owner": owner,
                                "deadline": dl.group(1) if dl else "未定"})
        if not actions:  # 兜底：带期限的句子
            for ln in _lines(text):
                dl = _DEADLINE_RE.search(ln)
                if dl and len(ln) >= 12:
                    actions.append({"item": ln[:80], "owner": "待定", "deadline": dl.group(1)})
                if len(actions) >= 6:
                    break
        summary = _first_para(text)
        if not summary and uniq:
            summary = f"本次周会共讨论 {len(uniq)} 个议题（" + "、".join(uniq[:4]) + "）"
            if actions:
                summary += f"，形成 {len(actions)} 条行动项"
            summary += "，要点见下方议题与行动项明细。"
        return summary, uniq, actions[:12]
