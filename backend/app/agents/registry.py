"""Agent 注册表：真实实装（B 工单完成）。fakes.build_fakes() 仍保留，便于回归对照。"""
from __future__ import annotations

from .analyst import AnalystAgent
from .base import AgentResult, AgentCtx, BaseAgent  # noqa: F401  (对外重导出)
from .copy import CopyAgent
from .docqa import DocQAAgent
from .fakes import build_fakes  # noqa: F401
from .minutes import MinutesAgent
from .voc import VocAgent


def build_registry() -> dict[str, BaseAgent]:
    return {
        "E1": AnalystAgent(),
        "E2": DocQAAgent(),
        "E3": MinutesAgent(),
        "E4": CopyAgent(),
        "E5": VocAgent(),
    }


REGISTRY: dict[str, BaseAgent] = build_registry()
