"""进程内 asyncio fan-out 事件总线（PLAN §5）。

事件格式：{type, run_id?, employee_id?, ts, payload}
- publish() 同步扇出到所有订阅者（asyncio.Queue），不阻塞生产者
- 同时按 run_id 环形缓冲最近事件，供任务时间线重放（GET /api/runs/{id}.events）
"""
from __future__ import annotations

import asyncio
import time
from collections import defaultdict, deque

EVENT_TYPES = [
    "run.created", "run.status",
    "step.started", "step.thinking", "step.output", "step.done",
    "approval.pending", "approval.decided",
    "employee.status", "usage.tick", "doc.indexed",
]
_REPLAY_CAP = 500


class EventBus:
    def __init__(self) -> None:
        self._subscribers: list[asyncio.Queue] = []
        self._replay: dict[str, deque] = defaultdict(lambda: deque(maxlen=_REPLAY_CAP))

    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=1000)
        self._subscribers.append(q)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        if q in self._subscribers:
            self._subscribers.remove(q)

    def publish(self, etype: str, *, run_id: str | None = None,
                employee_id: str | None = None, payload: dict | None = None) -> dict:
        event = {
            "type": etype,
            "run_id": run_id,
            "employee_id": employee_id,
            "ts": time.time(),
            "payload": payload or {},
        }
        if run_id:
            self._replay[run_id].append(event)
        for q in list(self._subscribers):
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                # 慢消费者：丢弃最旧一条再入队
                try:
                    q.get_nowait()
                    q.put_nowait(event)
                except asyncio.QueueEmpty:
                    pass
        return event

    def replay(self, run_id: str) -> list[dict]:
        return list(self._replay.get(run_id, []))


bus = EventBus()
