"""任务发起：调度长(SUP) 路由 → 建 Run → 引擎后台执行。"""
from __future__ import annotations

import json

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from ..agents.supervisor import classify as sup_classify
from ..bus import bus
from ..db import get_session
from ..llm import llm
from ..models import Document, Run
from ..sop.engine import SopEngine

router = APIRouter(tags=["tasks"])

_HINT_TO_CODE = {"analyze": "E1", "minutes": "E3", "voc": "E5", "copy": "E4", "qa": "E2"}


class TaskBody(BaseModel):
    kind: str = Field(pattern="^(file|text)$")
    doc_id: str | None = None
    text: str | None = None
    qa_doc_id: str | None = None
    hint: str | None = Field(default=None, description="analyze|minutes|voc|copy|qa（不传则启发式路由）")
    extra: dict = Field(default_factory=dict)


async def _route(body: TaskBody, doc: Document | None) -> tuple[str, dict, str]:
    """返回 (employee_code, agent_payload, 路由理由)。显式 hint 优先，否则调度长决策。"""
    if body.kind == "file":
        assert doc is not None
        payload = {"kind": "file", "doc_id": doc.id, "filename": doc.filename,
                   "file_kind": doc.kind, **body.extra}
        forced = _HINT_TO_CODE.get(body.hint or "")
        if forced:
            return forced, payload, f"用户指定路由 {forced}"
        code, why = await sup_classify(payload, llm)
        return code, payload, why
    # text
    text = (body.text or "").strip()
    if not text:
        raise HTTPException(400, "text 不能为空")
    if body.hint == "copy" or body.extra.get("copy"):
        return "E4", {"kind": "text", "text": text, "copy": True, **body.extra}, "用户指定路由 E4（文案改写）"
    if body.hint == "qa":
        return "E2", {"kind": "text", "text": text, "qa": True, "qa_doc_id": body.qa_doc_id}, "用户指定路由 E2（文档问答）"
    payload = {"kind": "text", "text": text, "qa": True, **body.extra}
    if body.qa_doc_id:
        payload["qa_doc_id"] = body.qa_doc_id
    code, why = await sup_classify(payload, llm)
    if code == "E4":
        payload["copy"] = True
    return code, payload, why


@router.post("/api/tasks", status_code=201)
async def create_task(body: TaskBody, background: BackgroundTasks,
                      session: AsyncSession = Depends(get_session())):
    doc = None
    if body.kind == "file":
        if not body.doc_id:
            raise HTTPException(400, "file 任务需要 doc_id")
        doc = await session.get(Document, body.doc_id)
        if doc is None:
            raise HTTPException(404, "document 不存在")
    code, payload, why = await _route(body, doc)
    title = (doc.filename if doc else (body.text or "")[:48]).strip() or "任务"
    trigger = "upload" if body.kind == "file" else "chat"
    run = Run(title=title, trigger=trigger, status="pending")
    session.add(run)
    await session.commit()
    await session.refresh(run)
    bus.publish("run.created", run_id=run.id,
                payload={"title": title, "trigger": trigger, "route": code, "route_reason": why})
    plan = [{"type": "employee", "employee_code": code,
             "input_summary": json.dumps(payload, ensure_ascii=False)[:512]}]
    engine = SopEngine(run.id)
    background.add_task(engine.start, plan)
    return {"run_id": run.id, "route": code, "title": title, "status": "pending"}
