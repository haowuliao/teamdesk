"""LLM 网关（PLAN §7）：OpenAI 兼容协议，统一 token 计量 → usage 表 + usage.tick 事件。"""
from __future__ import annotations

import logging
import time

from openai import APIConnectionError, APIStatusError, AsyncOpenAI, AuthenticationError
from openai import APITimeoutError

from .bus import bus
from .config import config

log = logging.getLogger("teamdesk.llm")


class LLMUnavailable(Exception):
    """无 key / 网络失败 / 4xx 等：agent 捕获后走离线降级。"""


# 粗略美元单价（demo 级估算，仅用于看板展示）
_COST_PER_MTOK: dict[str, tuple[float, float]] = {  # model_prefix: (in, out)
    "deepseek": (0.28, 0.42),
    "gpt": (2.5, 10.0),
    "qwen": (0.4, 1.2),
    "o1": (15.0, 60.0),
}


def _cost_estimate(model: str, tokens_in: int, tokens_out: int) -> float:
    for prefix, (ci, co) in _COST_PER_MTOK.items():
        if model.startswith(prefix):
            return round(tokens_in / 1e6 * ci + tokens_out / 1e6 * co, 6)
    return round(tokens_out / 1e6, 6)  # 未知模型：按输出量给个极小估值


def _count_tokens(text: str) -> int:
    # 无 tokenizer 依赖时的粗略估算：CJK 1 字≈1 token，ascii 4 字符≈1 token
    cjk = sum(1 for ch in text if ord(ch) > 0x2E7F)
    return cjk + max(0, len(text) - cjk) // 4 or 1


class LLMClient:
    def __init__(self) -> None:
        self._client: AsyncOpenAI | None = AsyncOpenAI(
            base_url=config.LLM_BASE_URL,
            api_key=config.LLM_API_KEY or "offline-placeholder",
        ) if config.LLM_API_KEY else None
        self.model: str = config.LLM_MODEL

    @property
    def online(self) -> bool:
        return self._client is not None

    async def chat(
        self,
        system: str,
        messages: list[dict],
        *,
        json_mode: bool = False,
        model: str | None = None,
        employee_id: str | None = None,
    ) -> tuple[str, int, int]:
        """返回 (text, tokens_in, tokens_out)；失败抛 LLMUnavailable，并自动记 usage。"""
        model = model or self.model
        t0 = time.monotonic()
        if not self.online:
            raise LLMUnavailable("LLM_API_KEY 未配置（离线模式）")
        try:
            kwargs: dict = {
                "model": model,
                "messages": ([{"role": "system", "content": system}] if system else []) + messages,
            }
            if json_mode:
                kwargs["response_format"] = {"type": "json_object"}
            resp = await self._client.chat.completions.create(**kwargs)
            text = (resp.choices[0].message.content or "").strip()
            if getattr(resp, "usage", None) is not None:
                ti = int(getattr(resp.usage, "prompt_tokens", 0) or 0)
                to = int(getattr(resp.usage, "completion_tokens", 0) or 0)
            else:
                ti = _count_tokens(system) + sum(_count_tokens(m.get("content", "")) for m in messages)
                to = _count_tokens(text)
        except (AuthenticationError, APIStatusError) as e:
            if isinstance(e, APIStatusError) and e.status_code >= 500:
                raise LLMUnavailable(f"LLM 服务端错误 {e.status_code}") from e
            raise LLMUnavailable(f"LLM 不可用: {e.__class__.__name__}") from e
        except (APITimeoutError, APIConnectionError) as e:
            raise LLMUnavailable(f"LLM 网络/超时: {e.__class__.__name__}") from e
        except Exception as e:  # 兜底：任何意外对 agent 都表现为"不可用"
            raise LLMUnavailable(f"LLM 意外错误: {e.__class__.__name__}") from e

        await self._record_usage(employee_id, model, ti, to)
        return text, ti, to

    async def _record_usage(self, employee_id: str | None, model: str, ti: int, to: int) -> None:
        cost = _cost_estimate(model, ti, to)
        # 短会话写 usage 表（不耦合请求级会话）
        try:
            from .db import SessionLocal
            from .models import Usage

            async with SessionLocal() as s:
                rec = Usage(
                    employee_id=employee_id, model=model,
                    tokens_in=ti, tokens_out=to, cost_est=cost,
                )
                s.add(rec)
                await s.commit()
        except Exception:  # 计量失败不应打断主流程
            log.exception("usage 记录失败")
        bus.publish("usage.tick", employee_id=employee_id,
                    payload={"model": model, "tokens_in": ti, "tokens_out": to,
                             "cost_est": cost, "latency_ms": int((time.monotonic() - t0) * 1000)})


llm = LLMClient()
