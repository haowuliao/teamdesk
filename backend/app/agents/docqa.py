"""E2 老查 · 文档问答官（PLAN §1/§4/§8）：制度/手册问答，答案必须带出处。

在线：RAG top5 作为唯一事实来源 → LLM 组织答案（json_mode），引用限定了检索到的 (doc, seq)。
离线：问题 n-gram 与切块句子做重叠打分，取最相关句子拼答案，引用同样落在检索结果上。
超纲（检索不到）时明确说查无条款，不编造。
"""
from __future__ import annotations

import re

from .base import AgentCtx, AgentResult, BaseAgent
from .common import _thinking


def _qgrams(q: str) -> set[str]:
    q = re.sub(r"[？?！!。，,\s]+", " ", q or "").strip().lower()
    grams: set[str] = set()
    for tok in q.split():
        if re.fullmatch(r"[a-z0-9.%℃]+", tok):
            grams.add(tok)
        else:
            for i in range(len(tok) - 1):
                grams.add(tok[i:i + 2])
    return grams


def _sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[。！？!?；;\n])", text or "")
    return [p.strip() for p in parts if len(p.strip()) >= 6]


class DocQAAgent(BaseAgent):
    code = "E2"

    async def plan_hint(self, p: dict) -> bool:
        if p.get("kind") != "text":
            return False
        return bool(p.get("qa") or p.get("qa_doc_id"))

    async def execute(self, ctx: AgentCtx) -> AgentResult:
        question = str((ctx.payload or {}).get("text") or "").strip()
        if not question:
            raise RuntimeError("老查需要一个文本问题")
        qa_doc_id = (ctx.payload or {}).get("qa_doc_id")

        _thinking(ctx, f"问题向量化，在知识库检索 top5（限定范围={'是' if qa_doc_id else '全库'}）…")
        hits = await ctx.rag.search(question, top_k=5, doc_id=qa_doc_id)
        if not hits:
            return AgentResult(
                output={"answer": "知识库目前还没有可检索的内容，请先上传制度/手册类文档。",
                        "citations": []},
                reasoning="[离线模式] 知识库为空，无可检索内容，如实告知不编造",
            )
        _thinking(ctx, f"命中 {len(hits)} 个候选片段（最高相似度 {hits[0]['score']:.3f}）")

        grams = _qgrams(question)
        by_key = {}
        for h in hits:
            key = (h["doc_name"], h["seq"])
            sents = _sentences(h["content"])
            best = max(((self._ov(grams, s), s) for s in sents), default=(0, ""))[1]
            by_key[key] = {"doc_name": h["doc_name"], "seq": h["seq"], "score": h["score"],
                           "snippet": (best or h["content"])[:120], "_ov": self._ov(grams, best)}

        offline = False
        try:
            answer, cited_keys = await self._ask_llm(ctx, question, hits)
        except Exception:
            offline = True
            answer, cited_keys = self._offline_answer(question, by_key)

        cites = []
        for key in cited_keys if cited_keys else list(by_key.keys())[:2]:
            if key in by_key:
                cites.append({k: v for k, v in by_key[key].items() if not k.startswith("_")})
        if not cites:
            top = sorted(by_key.values(), key=lambda x: x["_ov"], reverse=True)[:2]
            cites = [{k: v for k, v in t.items() if not k.startswith("_")} for t in top]

        if not answer:
            answer = ("知识库中没有找到与该问题直接相关的条款（最相近片段：『"
                      f"{cites[0]['snippet'][:40]}…』），建议补充对应文档后再问。")
        reasoning = (f"检索 top5 → 命中 {len(by_key)} 个片段 → "
                     + ("LLM 基于片段组织答案" if not offline else
                        "[离线模式] 无 LLM，按问题词重叠取最相关条款句"
                        )) + f" → 引用 {len(cites)} 处（来源: 文件名#段seq）"
        return AgentResult(output={"answer": answer, "citations": cites}, reasoning=reasoning)

    # ---------------- 内部 ----------------

    @staticmethod
    def _ov(grams: set[str], s: str) -> int:
        low = (s or "").lower()
        return sum(1 for g in grams if g in low)

    def _offline_answer(self, question: str, by_key: dict) -> tuple[str, list[tuple[str, int]]]:
        cand = []
        for key, meta in by_key.items():
            if meta["_ov"] > 0:
                cand.append((meta["_ov"], key))
        if not cand:
            return "", []
        cand.sort(reverse=True)
        picked = [key for ov, key in cand[:2]]
        sents = [by_key[k]["snippet"] for k in picked]
        answer = "根据知识库相关条款：" + "；".join(s.strip("。；； ") for s in sents) + "。"
        return answer, picked

    async def _ask_llm(self, ctx: AgentCtx, question: str, hits: list[dict]) -> tuple[str, list[tuple[str, int]]]:
        import json

        material = "\n\n".join(
            f"[片段{i + 1}]（{h['doc_name']}#段{h['seq']}，相似度{h['score']}）\n{h['content'][:400]}"
            for i, h in enumerate(hits))
        system = ("你是企业内部制度问答员。只能依据用户提供的片段作答，禁止使用片段外的知识；"
                  "片段没覆盖的问题要明说查无条款。只输出 JSON："
                  '{"answer": "...", "citations": [{"doc_name": "...", "seq": 0}]}，'
                  "citations 只能来自片段标注的 (doc_name, seq)。")
        text, _, _ = await ctx.llm.chat(
            system,
            [{"role": "user", "content": f"知识库片段：\n{material}\n\n问题：{question}"}],
            json_mode=True, employee_id=emp_id_of(ctx))
        t = text.strip()
        if t.startswith("```"):
            t = t.strip("`").lstrip("json").strip()
        try:
            data = json.loads(t)
        except Exception:
            i, j = t.find("{"), t.rfind("}")
            if not (0 <= i < j):
                raise
            data = json.loads(t[i:j + 1])
        answer = str(data.get("answer", "")).strip()
        valid = {(h["doc_name"], h["seq"]) for h in hits}
        cited = []
        for c in data.get("citations") or []:
            if isinstance(c, dict):
                key = (str(c.get("doc_name", "")), int(c.get("seq", -1)))
                if key in valid and key not in cited:
                    cited.append(key)
        return answer, cited


def emp_id_of(ctx: AgentCtx) -> str | None:
    return ctx.employee.get("id") if isinstance(ctx.employee, dict) else None
