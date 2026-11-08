"""审批队列/决策（PLAN §6）。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_session
from ..models import Approval, Employee, Run, Step
from ..sop.engine import ENGINES, recover
from ..sop.states import IllegalTransition

router = APIRouter(tags=["approvals"])


class DecideBody(BaseModel):
    decision: str  # approve | reject
    note: str = ""
    decided_by: str = "boss"


@router.get("/api/approvals")
async def list_approvals(status: str | None = None, session: AsyncSession = Depends(get_session())):
    stmt = select(Approval).order_by(Approval.id.desc()).limit(100)
    if status:
        stmt = stmt.where(Approval.status == status)
    apprs = (await session.execute(stmt)).scalars().all()
    out = []
    for a in apprs:
        step = await session.get(Step, a.step_id)
        run = await session.get(Run, a.run_id)
        emp_code = None
        if step and step.employee_id:
            emp = await session.get(Employee, step.employee_id)
            emp_code = emp.code if emp else None
        out.append({
            "id": a.id, "run_id": a.run_id, "step_id": a.step_id,
            "run_title": run.title if run else None,
            "employee_code": emp_code,
            "payload": a.payload, "risk_note": a.risk_note, "status": a.status,
            "decided_by": a.decided_by, "note": a.note,
            "decided_at": a.decided_at.isoformat() if a.decided_at else None,
        })
    return {"approvals": out}


@router.post("/api/approvals/{approval_id}/decide")
async def decide(approval_id: str, body: DecideBody, session: AsyncSession = Depends(get_session())):
    appr = await session.get(Approval, approval_id)
    if appr is None:
        raise HTTPException(404, "approval 不存在")
    if appr.status != "pending":
        raise HTTPException(409, f"approval 已决: {appr.status}")
    engine = ENGINES.get(appr.run_id)
    if engine is None:
        # 进程重启后的兜底：重建引擎壳
        await recover()
        engine = ENGINES.get(appr.run_id)
    if engine is None:
        raise HTTPException(409, "run 引擎不可用（请重启服务触发恢复）")
    try:
        await engine.resume(approval_id, body.decision, body.note, body.decided_by)
    except (ValueError, IllegalTransition) as e:
        raise HTTPException(409, str(e)) from e
    await session.refresh(appr)  # 引擎已用独立会话提交，强制重读最新值
    return {"id": appr.id, "status": appr.status, "decided_by": appr.decided_by, "note": appr.note}
