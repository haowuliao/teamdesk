"""SSE 单通道事件流（PLAN §5）。"""
from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter
from sse_starlette.sse import EventSourceResponse

from ..bus import bus

router = APIRouter(tags=["events"])


@router.get("/api/events")
async def events():
    async def gen():
        q = bus.subscribe()
        try:
            yield {"event": "connected", "data": json.dumps({"ok": True})}
            while True:
                ev = await q.get()
                yield {"data": json.dumps(ev, ensure_ascii=False)}
        except asyncio.CancelledError:
            raise
        finally:
            bus.unsubscribe(q)

    return EventSourceResponse(gen(), ping=20)
