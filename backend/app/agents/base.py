"""Agent 契约（PLAN §4，原文照抄实现）。"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class AgentCtx:
    run_id: str
    step_id: str
    employee: object          # EmployeeRow（ORM 对象，可能为空占位）
    payload: dict             # {kind: "file"|"text", doc_id?, text?, extra?}
    bus: object               # EventBus
    llm: object               # LLMClient
    rag: object               # RAGStore


@dataclass
class AgentResult:
    output: dict              # 结构化产物: {insights[], chart?: EChartsOption, citations[], ...}
    reasoning: str            # 展示在时间线里的"思路"
    needs_approval: bool = False  # True 时引擎自动追加 approval 步
    approval_payload: dict | None = field(default=None)


class BaseAgent:
    code: str = "BASE"

    async def plan_hint(self, p: dict) -> bool:
        """供 supervisor 路由打分（静态规则即可）。"""
        return False

    async def execute(self, ctx: AgentCtx) -> AgentResult:
        raise NotImplementedError
