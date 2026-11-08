"""SOP 引擎（PLAN §3）：顺序驱动 Run 中的 Step，支持 employee / approval / condition 三类，
审批 park/resume，全程落库 + 发事件。

用法：
    engine = SopEngine(run_id)
    await engine.start(plan=[{"type":"employee","employee_code":"E1","input_summary":"..."}, ...])
    ...稍后（另一请求）...
    await ENGINES[run_id].resume(approval_id, "approve", note="", decided_by="boss")
"""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..agents.base import AgentCtx
from ..agents.registry import REGISTRY
from ..bus import bus
from ..db import SessionLocal
from ..llm import llm
from ..models import Approval, Employee, Run, Step
from ..rag import rag
from . import states

log = logging.getLogger("teamdesk.engine")


def _now() -> datetime:
    return datetime.now(timezone.utc)


# 活着的引擎（同一进程内 resume 用；waiting_human 的 run 重启后由 recover() 重建空引擎壳）
ENGINES: dict[str, "SopEngine"] = {}


async def _get(session: AsyncSession, model, pk: str):
    return await session.get(model, pk)


async def _set(session: AsyncSession, obj, **fields) -> None:
    for k, v in fields.items():
        setattr(obj, k, v)
    await session.commit()


class SopEngine:
    def __init__(self, run_id: str) -> None:
        self.run_id = run_id
        self._lock = asyncio.Lock()
        self._parked_step_idx: int | None = None
        self._skip: set[int] = set()

    # ---------------- 启动 ----------------

    async def start(self, plan: list[dict]) -> None:
        """plan 元素: {type, employee_code?, input_summary?, flag_key?, skip_if_true?, skip_targets?}"""
        ENGINES[self.run_id] = self
        async with self._lock:
            async with SessionLocal() as s:
                for i, spec in enumerate(plan):
                    emp_id = None
                    code = spec.get("employee_code")
                    if code:
                        row = (await s.execute(select(Employee).where(Employee.code == code))).scalar_one_or_none()
                        emp_id = row.id if row else None
                    s.add(Step(run_id=self.run_id, idx=i, type=spec["type"], employee_id=emp_id,
                               input_summary=str(spec.get("input_summary", ""))[:512],
                               flag_key=spec.get("flag_key"),
                               skip_if_true=bool(spec.get("skip_if_true", True)),
                               skip_targets=spec.get("skip_targets")))
                await s.commit()
            await self._set_run(status="running")
            bus.publish("run.status", run_id=self.run_id, payload={"status": "running"})
            await self._execute_from(0)

    # ---------------- 审批恢复 ----------------

    async def resume(self, approval_id: str, decision: str, note: str = "", decided_by: str = "boss") -> None:
        if decision not in ("approve", "reject"):
            raise ValueError("decision 必须是 approve/reject")
        async with self._lock:
            async with SessionLocal() as s:
                appr = await s.get(Approval, approval_id)
                if appr is None or appr.status != "pending":
                    raise ValueError("approval 不存在或已决")
                step_id, run_status = appr.step_id, None
                run = await s.get(Run, appr.run_id)
                run_status = run.status if run else None
                if run_status != "waiting_human":
                    raise ValueError("run 不在等待审批状态")
                appr.status = "approved" if decision == "approve" else "rejected"
                appr.decided_by = decided_by
                appr.note = note or ""
                appr.decided_at = _now()
                step_row = await s.get(Step, appr.step_id)
                step_idx = step_row.idx if step_row else None
                # run/step 状态变更延后到 _finalize_decide（需要事件顺序正确）
                await s.commit()
            bus.publish("approval.decided", run_id=appr.run_id,
                        payload={"approval_id": approval_id, "decision": decision,
                                 "decided_by": decided_by, "note": note})
            if decision == "reject":
                await self._set_step(step_id, status="error", output={"decision": "rejected"},
                                     reasoning=f"审批被 {decided_by} 拒绝: {note or '无理由'}", finished_at=_now())
                await self._set_run(status="error", reason="rejected", finished_at=_now())
                bus.publish("run.status", run_id=appr.run_id, payload={"status": "error", "reason": "rejected"})
                return
            # approve：续跑
            await self._set_step(step_id, status="completed", output={"decision": "approved", "note": note},
                                 reasoning=f"审批通过（{decided_by}）", finished_at=_now())
            await self._set_run(status="running", finished_at=None)
            bus.publish("run.status", run_id=appr.run_id, payload={"status": "running", "resumed": True})
            await self._execute_from((step_idx or 0) + 1)

    # ---------------- 内部执行 ----------------

    async def _execute_from(self, start_idx: int) -> None:
        assert self._lock.locked()
        try:
            idx = start_idx
            while True:
                async with SessionLocal() as s:
                    row = (await s.execute(
                        select(Step).where(Step.run_id == self.run_id, Step.idx == idx)
                        .order_by(Step.idx.asc()))).scalars().first()
                if row is None:
                    break
                if row.status in ("completed", "error", "cancelled"):
                    idx += 1
                    continue
                if idx in self._skip:
                    await self._set_step(row.id, status="completed", output={"skipped": True},
                                         reasoning="被 condition 步跳过", finished_at=_now())
                    bus.publish("step.done", run_id=self.run_id,
                                payload={"step_id": row.id, "idx": row.idx, "skipped": True,
                                         "status": "completed"})
                    idx += 1
                    continue
                await self._run_step(row)
                if self._parked_step_idx is not None:
                    return  # 停在审批
                idx += 1
            await self._set_run(status="completed", finished_at=_now())
            bus.publish("run.status", run_id=self.run_id, payload={"status": "completed"})
        except Exception as e:
            log.exception("run %s 执行失败", self.run_id)
            try:
                states.assert_transition("running", "error")
            except states.IllegalTransition:
                pass
            await self._set_run(status="error", reason=str(e)[:256], finished_at=_now())
            bus.publish("run.status", run_id=self.run_id, payload={"status": "error", "reason": str(e)[:256]})

    async def _run_step(self, step: Step) -> None:
        if step.type == "condition":
            await self._run_condition(step)
            return
        if step.type == "approval":
            await self._park_for_approval(step)
            return
        if step.type == "employee":
            await self._run_employee(step)
            return
        await self._set_step(step.id, status="error", reasoning=f"未知 step 类型: {step.type}", finished_at=_now())
        bus.publish("step.done", run_id=self.run_id,
                    payload={"step_id": step.id, "idx": step.idx, "status": "error"})

    async def _run_employee(self, step: Step) -> None:
        emp_code = None
        if step.employee_id:
            async with SessionLocal() as s:
                emp = await s.get(Employee, step.employee_id)
                emp_code = emp.code if emp else None
        agent = REGISTRY.get(emp_code or "") if emp_code else None
        if agent is None:
            await self._set_step(step.id, status="error",
                                 reasoning=f"未注册的员工代号: {emp_code}", finished_at=_now())
            bus.publish("step.done", run_id=self.run_id,
                        payload={"step_id": step.id, "idx": step.idx, "status": "error"})
            raise RuntimeError(f"employee not found: {emp_code}")

        payload = self._build_payload(step)
        bus.publish("step.started", run_id=self.run_id, employee_id=step.employee_id,
                    payload={"step_id": step.id, "idx": step.idx, "code": emp_code,
                             "input_summary": step.input_summary})
        await self._set_step(step.id, status="running", started_at=_now())
        if step.employee_id:
            bus.publish("employee.status", employee_id=step.employee_id, payload={"status": "active"})
            await self._set_employee(step.employee_id, status="active")

        try:
            ctx = AgentCtx(run_id=self.run_id, step_id=step.id, employee=None,
                           payload=payload, bus=bus, llm=llm, rag=rag)
            # 补上 employee 轻量快照（避免 ORM 对象跨会话失效；字段见 EmployeeRow 约定）
            if step.employee_id:
                async with SessionLocal() as s:
                    emp_row = await s.get(Employee, step.employee_id)
                    ctx.employee = (
                        {"id": emp_row.id, "code": emp_row.code, "name": emp_row.name,
                         "emoji": emp_row.emoji, "title": emp_row.title, "model": emp_row.model,
                         "persona": emp_row.persona, "permissions": emp_row.permissions}
                        if emp_row else None
                    )
            result = await agent.execute(ctx)
            tokens = 0
            out = result.output or {}
            await self._set_step(step.id, status="completed", output=out,
                                 reasoning=result.reasoning or "", tokens=tokens,
                                 finished_at=_now())
            bus.publish("step.output", run_id=self.run_id, employee_id=step.employee_id,
                        payload={"step_id": step.id, "idx": step.idx, "code": emp_code, "output": out})
            bus.publish("step.done", run_id=self.run_id, employee_id=step.employee_id,
                        payload={"step_id": step.id, "idx": step.idx, "code": emp_code, "status": "completed"})
            # 引擎自动追加 approval 步（契约：needs_approval=True 且下一步不是 approval）
            if result.needs_approval:
                await self._append_approval_after(step, getattr(result, "approval_payload", None))
        except Exception as e:
            log.exception("employee step %s 失败", step.id)
            if step.employee_id:
                bus.publish("employee.status", employee_id=step.employee_id, payload={"status": "error"})
                await self._set_employee(step.employee_id, status="error")
            await self._set_step(step.id, status="error", reasoning=f"执行失败: {e}"[:2000], finished_at=_now())
            bus.publish("step.done", run_id=self.run_id, employee_id=step.employee_id,
                        payload={"step_id": step.id, "idx": step.idx, "status": "error", "error": str(e)[:200]})
            raise
        finally:
            if step.employee_id:
                bus.publish("employee.status", employee_id=step.employee_id, payload={"status": "standby"})
                await self._set_employee(step.employee_id, status="standby")

    def _build_payload(self, step: Step) -> dict:
        """从 input_summary（JSON）还原 payload；失败则退化为 {kind:text,text:input_summary}"""
        raw = (step.input_summary or "").strip()
        try:
            data = json.loads(raw)
            if isinstance(data, dict):
                return data
        except (json.JSONDecodeError, TypeError):
            pass
        return {"kind": "text", "text": raw}

    async def _park_for_approval(self, step: Step) -> None:
        payload = {}
        risk = step.input_summary or "关键动作需人工确认"
        try:
            data = json.loads(step.input_summary or "{}")
            if isinstance(data, dict):
                payload = data.get("payload") or data
                risk = data.get("risk_note", risk)
        except (json.JSONDecodeError, TypeError):
            pass
        async with SessionLocal() as s:
            exists = (await s.execute(
                select(Approval).where(Approval.step_id == step.id))).scalar_one_or_none()
            if exists is None:
                s.add(Approval(run_id=self.run_id, step_id=step.id,
                               payload=payload, risk_note=str(risk)[:500]))
                await s.commit()
                appr_id = None
        # 取回 id
        async with SessionLocal() as s:
            appr = (await s.execute(select(Approval).where(Approval.step_id == step.id))).scalar_one()
            appr_id = appr.id
        states.assert_transition("running", "waiting_human")
        await self._set_run(status="waiting_human")
        await self._set_step(step.id, status="running", started_at=_now())
        await self._set_step(step.id, status="waiting_human")
        bus.publish("run.status", run_id=self.run_id, payload={"status": "waiting_human"})
        bus.publish("approval.pending", run_id=self.run_id,
                    payload={"approval_id": appr_id, "step_id": step.id, "idx": step.idx,
                             "risk_note": str(risk)[:500], "payload": payload})
        self._parked_step_idx = step.idx

    async def _append_approval_after(self, step: Step, approval_payload: dict | None) -> None:
        approval_payload = approval_payload or {}
        async with SessionLocal() as s:
            nxt = (await s.execute(
                select(Step).where(Step.run_id == self.run_id, Step.idx > step.idx)
                .order_by(Step.idx.asc()))).scalars().first()
            if nxt is not None and nxt.type == "approval":
                return  # 计划里已排了审批
            max_idx = (await s.execute(
                select(Step).where(Step.run_id == self.run_id)
                .order_by(Step.idx.desc()))).scalars().first()
            new_idx = (max_idx.idx + 1) if max_idx is not None else step.idx + 1
            s.add(Step(run_id=self.run_id, idx=new_idx, type="approval", employee_id=step.employee_id,
                       input_summary=json.dumps({"risk_note": approval_payload.get("risk_note", "关键动作需人工确认"),
                                                  "payload": approval_payload}, ensure_ascii=False)[:512]))
            await s.commit()

    async def _run_condition(self, step: Step) -> None:
        """读最近一个已完成 employee 步 output 的 flag_key；为真(且 skip_if_true)则跳过 skip_targets。"""
        flag = False
        async with SessionLocal() as s:
            prevs = (await s.execute(
                select(Step).where(Step.run_id == self.run_id, Step.type == "employee", Step.status == "completed")
                .order_by(Step.idx.desc()))).scalars().all()
            for p in prevs:
                if p.output and isinstance(p.output, dict) and step.flag_key and step.flag_key in p.output:
                    flag = bool(p.output[step.flag_key])
                    break
        skip = flag if step.skip_if_true else (not flag)
        if skip and step.skip_targets:
            self._skip.update(int(t) for t in step.skip_targets)
        await self._set_step(step.id, status="completed",
                             output={"flag": flag, "skip": skip},
                             reasoning=f"condition: {step.flag_key}={flag} → {'跳过 ' + str(step.skip_targets) if skip else '不跳过'}",
                             finished_at=_now())
        bus.publish("step.done", run_id=self.run_id,
                    payload={"step_id": step.id, "idx": step.idx, "status": "completed",
                             "flag": flag, "skip": skip})

    # ---------------- 小工具 ----------------

    async def _set_run(self, **fields) -> None:
        async with SessionLocal() as s:
            run = await s.get(Run, self.run_id)
            if run is not None:
                cur = run.status
                if "status" in fields:
                    states.assert_transition(cur, fields["status"])
                for k, v in fields.items():
                    setattr(run, k, v)
                await s.commit()

    async def _set_step(self, step_id: str, **fields) -> None:
        async with SessionLocal() as s:
            st = await s.get(Step, step_id)
            if st is not None:
                if "status" in fields:
                    states.assert_transition(st.status, fields["status"])
                for k, v in fields.items():
                    setattr(st, k, v)
                await s.commit()

    async def _set_employee(self, employee_id: str, **fields) -> None:
        async with SessionLocal() as s:
            emp = await s.get(Employee, employee_id)
            if emp is not None:
                for k, v in fields.items():
                    setattr(emp, k, v)
                await s.commit()


async def recover() -> None:
    """启动恢复：running/pending 的 run 标记为中断；waiting_human 的 run 挂空引擎壳以便 resume。"""
    async with SessionLocal() as s:
        broken = (await s.execute(
            select(Run).where(Run.status.in_(["running", "pending"])))).scalars().all()
        for r in broken:
            r.status = "error"
            r.reason = "process restart（M1 不支持执行中步自动续跑）"
            r.finished_at = _now()
        if broken:
            await s.commit()
        parked = (await s.execute(
            select(Run).where(Run.status == "waiting_human"))).scalars().all()
        for r in parked:
            ENGINES.setdefault(r.id, SopEngine(r.id))
        # 卡住的 employee 状态复位
        actives = (await s.execute(
            select(Employee).where(Employee.status.in_(["active", "error"])))).scalars().all()
        for e in actives:
            e.status = "standby"
        if actives:
            await s.commit()
