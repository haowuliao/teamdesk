"""员工列表/详情（含聚合 metrics，PLAN §6）。"""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_session
from ..models import Employee, Step, Usage

router = APIRouter(tags=["employees"])


async def _employee_metrics(session: AsyncSession, emp: Employee) -> dict:
    """任务数/成功率/平均耗时/今日任务数/tokens/花费 —— M1 在 Python 侧聚合（demo 数据量足够）。"""
    rows = (await session.execute(
        select(Step).where(Step.type == "employee", Step.employee_id == emp.id)
        .order_by(Step.started_at.desc()).limit(500))).scalars().all()

    def _naive(dt):
        return dt.replace(tzinfo=None) if dt is not None and dt.tzinfo is not None else dt

    total = len(rows)
    done = [r for r in rows if r.status == "completed"]
    ok = [r for r in done if not (isinstance(r.output, dict) and r.output.get("skipped"))]
    errs = [r for r in rows if r.status in ("error", "cancelled")]
    dur = [(r.finished_at - r.started_at).total_seconds()
           for r in done if r.started_at and r.finished_at]
    today_start = _naive(datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0))
    today = sum(1 for r in rows if r.started_at and _naive(r.started_at) >= today_start)
    urows = (await session.execute(
        select(Usage).where(Usage.employee_id == emp.id))).scalars().all()
    tokens_in = sum(u.tokens_in for u in urows)
    tokens_out = sum(u.tokens_out for u in urows)
    return {
        "tasks_total": total,
        "tasks_today": today,
        "success_rate": round(len(ok) / len(done), 3) if done else None,
        "avg_seconds": round(sum(dur) / len(dur), 1) if dur else None,
        "errors": len(errs),
        "tokens_in": tokens_in,
        "tokens_out": tokens_out,
        "cost_est": round(sum(u.cost_est for u in urows), 6),
    }


def _serialize(emp: Employee, metrics: dict, *, with_persona: bool = False) -> dict:
    data = {
        "id": emp.id, "code": emp.code, "name": emp.name, "emoji": emp.emoji,
        "title": emp.title, "jd": emp.jd, "permissions": emp.permissions or {},
        "model": emp.model, "status": emp.status, "created_at": emp.created_at.isoformat(),
        "metrics": metrics,
    }
    if with_persona:
        data["persona"] = emp.persona
    return data


@router.get("/api/employees")
async def list_employees(session: AsyncSession = Depends(get_session())):
    emps = (await session.execute(select(Employee).order_by(Employee.code))).scalars().all()
    return {"employees": [_serialize(e, await _employee_metrics(session, e)) for e in emps]}


@router.get("/api/employees/{code}")
async def get_employee(code: str, session: AsyncSession = Depends(get_session())):
    emp = (await session.execute(select(Employee).where(Employee.code == code))).scalar_one_or_none()
    if emp is None:
        raise HTTPException(404, f"员工不存在: {code}")
    return _serialize(emp, await _employee_metrics(session, emp), with_persona=True)
