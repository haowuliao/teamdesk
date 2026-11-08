"""Run 列表/详情（含 step 明细与事件重放，PLAN §6）。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..bus import bus
from ..db import get_session
from ..models import Approval, Run, Step

router = APIRouter(tags=["runs"])


def _run_brief(r: Run, step_total: int, step_done: int) -> dict:
    return {
        "id": r.id, "title": r.title, "trigger": r.trigger, "status": r.status,
        "reason": r.reason, "created_at": r.created_at.isoformat(),
        "finished_at": r.finished_at.isoformat() if r.finished_at else None,
        "parent_id": r.parent_id, "steps_total": step_total, "steps_done": step_done,
    }


def _step_detail(st: Step, emp_code: str | None) -> dict:
    return {
        "id": st.id, "idx": st.idx, "type": st.type,
        "employee_id": st.employee_id, "employee_code": emp_code,
        "input_summary": st.input_summary, "output": st.output, "reasoning": st.reasoning,
        "status": st.status, "tokens": st.tokens,
        "started_at": st.started_at.isoformat() if st.started_at else None,
        "finished_at": st.finished_at.isoformat() if st.finished_at else None,
        "flag_key": st.flag_key, "skip_targets": st.skip_targets,
    }


async def _steps_of(session: AsyncSession, run_id: str) -> tuple[list[Step], dict[str, str]]:
    steps = (await session.execute(
        select(Step).where(Step.run_id == run_id).order_by(Step.idx))).scalars().all()
    code_map: dict[str, str] = {}
    ids = {s.employee_id for s in steps if s.employee_id}
    if ids:
        from ..models import Employee
        emps = (await session.execute(select(Employee).where(Employee.id.in_(ids)))).scalars().all()
        code_map = {e.id: e.code for e in emps}
    return steps, code_map


@router.get("/api/runs")
async def list_runs(limit: int = 30, session: AsyncSession = Depends(get_session())):
    limit = max(1, min(limit, 100))
    runs = (await session.execute(select(Run).order_by(Run.created_at.desc()).limit(limit))).scalars().all()
    out = []
    for r in runs:
        steps, _ = await _steps_of(session, r.id)
        out.append(_run_brief(r, len(steps), sum(1 for s in steps if s.status == "completed")))
    return {"runs": out}


@router.get("/api/runs/{run_id}")
async def get_run(run_id: str, session: AsyncSession = Depends(get_session())):
    run = await session.get(Run, run_id)
    if run is None:
        raise HTTPException(404, "run 不存在")
    steps, code_map = await _steps_of(session, run_id)
    approvals = (await session.execute(
        select(Approval).where(Approval.run_id == run_id).order_by(Approval.id))).scalars().all()
    events = bus.replay(run_id)
    if not events:
        # 进程重启后无内存事件 → 用 step 行合成最小重放序列（看板仍可回放）
        events = []
        for s in steps:
            events.append({"type": "step.started", "run_id": run_id,
                           "employee_id": s.employee_id, "ts": (s.started_at.timestamp() if s.started_at else 0),
                           "payload": {"step_id": s.id, "idx": s.idx, "input_summary": s.input_summary}})
            events.append({"type": "step.done", "run_id": run_id,
                           "employee_id": s.employee_id, "ts": (s.finished_at.timestamp() if s.finished_at else 0),
                           "payload": {"step_id": s.id, "idx": s.idx, "status": s.status, "output": s.output}})
        events.append({"type": "run.status", "run_id": run_id, "ts": (run.finished_at.timestamp() if run.finished_at else 0),
                       "payload": {"status": run.status, "reason": run.reason, "replayed_from_db": True}})
    return {
        "run": _run_brief(run, len(steps), sum(1 for s in steps if s.status == "completed")),
        "steps": [_step_detail(s, code_map.get(s.employee_id or "")) for s in steps],
        "approvals": [{
            "id": a.id, "step_id": a.step_id, "payload": a.payload, "risk_note": a.risk_note,
            "status": a.status, "decided_by": a.decided_by, "note": a.note,
            "decided_at": a.decided_at.isoformat() if a.decided_at else None,
        } for a in approvals],
        "events": events,
    }
