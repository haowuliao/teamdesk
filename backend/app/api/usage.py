"""用量/绩效驾驶舱数据（PLAN §6）。"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_session
from ..models import Employee, Usage

router = APIRouter(tags=["usage"])


@router.get("/api/usage/summary")
async def usage_summary(days: int = 7, session: AsyncSession = Depends(get_session())):
    days = max(1, min(days, 90))
    since = datetime.now(timezone.utc) - timedelta(days=days)
    emps = (await session.execute(select(Employee).order_by(Employee.code))).scalars().all()
    from ..api.employees import _employee_metrics as metrics_fn

    per_employee = []
    for e in emps:
        m = await metrics_fn(session, e)
        per_employee.append({
            "code": e.code, "name": e.name, "emoji": e.emoji, "title": e.title,
            "tokens_in": m["tokens_in"], "tokens_out": m["tokens_out"],
            "cost_est": m["cost_est"], "tasks": m["tasks_total"],
            "success_rate": m["success_rate"], "avg_seconds": m["avg_seconds"],
        })

    urows = (await session.execute(
        select(Usage).where(Usage.ts >= since).order_by(Usage.ts.desc()))).scalars().all()
    # 按天聚合趋势
    by_day: dict[str, dict] = {}
    for u in urows:
        day = u.ts.strftime("%Y-%m-%d")
        d = by_day.setdefault(day, {"date": day, "tokens": 0, "cost_est": 0.0, "calls": 0})
        d["tokens"] += u.tokens_in + u.tokens_out
        d["cost_est"] += u.cost_est
        d["calls"] += 1
    trend = [by_day[k] for k in sorted(by_day)]
    for t in trend:
        t["cost_est"] = round(t["cost_est"], 6)
    recent = [{
        "id": u.id, "ts": u.ts.isoformat(), "employee_code": None, "model": u.model,
        "tokens_in": u.tokens_in, "tokens_out": u.tokens_out, "cost_est": u.cost_est,
    } for u in urows[:10]]
    # 给 recent 补员工代号
    if recent:
        emp_ids = {u.employee_id for u in urows[:10] if u.employee_id}
        if emp_ids:
            e2c = {e.id: e.code for e in (await session.execute(
                select(Employee).where(Employee.id.in_(emp_ids)))).scalars().all()}
            for i, u in enumerate(urows[:10]):
                recent[i]["employee_code"] = e2c.get(u.employee_id)
    totals = {"tokens_in": sum(u.tokens_in for u in urows),
              "tokens_out": sum(u.tokens_out for u in urows),
              "cost_est": round(sum(u.cost_est for u in urows), 6),
              "calls": len(urows)}
    return {"window_days": days, "totals": totals, "trend": trend,
            "per_employee": per_employee, "recent": recent}
