"""SQLAlchemy 2.0 async 数据模型。严格对应 PLAN.md §2 表结构。"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def new_id() -> str:
    return uuid.uuid4().hex


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class Employee(Base):
    __tablename__ = "employee"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    code: Mapped[str] = mapped_column(String(16), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    emoji: Mapped[str] = mapped_column(String(16), default="🤖")
    title: Mapped[str] = mapped_column(String(128), nullable=False)
    jd: Mapped[str] = mapped_column(Text, default="")
    persona: Mapped[str] = mapped_column(Text, default="")
    permissions: Mapped[dict] = mapped_column(JSON, default=dict)  # {autonomous[], approval_required[], forbidden[]}
    model: Mapped[str | None] = mapped_column(String(128), nullable=True)  # 空=继承全局
    status: Mapped[str] = mapped_column(String(16), default="standby")  # standby|active|paused|error
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Document(Base):
    __tablename__ = "document"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    filename: Mapped[str] = mapped_column(String(256), nullable=False)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)  # xlsx|csv|pdf|txt|md
    size: Mapped[int] = mapped_column(Integer, default=0)
    rows: Mapped[int | None] = mapped_column(Integer, nullable=True)
    text_preview: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    indexed: Mapped[bool] = mapped_column(Boolean, default=False)


class Chunk(Base):
    __tablename__ = "chunk"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    doc_id: Mapped[str] = mapped_column(ForeignKey("document.id"), index=True, nullable=False)
    seq: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    embedding_ref: Mapped[str] = mapped_column(Text, default="")  # 向量本体存 SQLite（numpy 序列化 hex）
    score: Mapped[float | None] = mapped_column(Float, nullable=True)  # 预留：最近一次检索分


class Run(Base):
    __tablename__ = "run"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    title: Mapped[str] = mapped_column(String(256), default="")
    trigger: Mapped[str] = mapped_column(String(16), default="manual")  # upload|chat|manual
    status: Mapped[str] = mapped_column(String(16), default="pending", index=True)
    # pending|running|waiting_human|completed|error|cancelled
    reason: Mapped[str | None] = mapped_column(String(256), nullable=True)  # 如 rejected / 错误信息
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    parent_id: Mapped[str | None] = mapped_column(ForeignKey("run.id"), nullable=True)


class Step(Base):
    __tablename__ = "step"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    run_id: Mapped[str] = mapped_column(ForeignKey("run.id"), index=True, nullable=False)
    idx: Mapped[int] = mapped_column(Integer, nullable=False)
    type: Mapped[str] = mapped_column(String(16), nullable=False)  # employee|approval|condition
    employee_id: Mapped[str | None] = mapped_column(ForeignKey("employee.id"), nullable=True)
    input_summary: Mapped[str] = mapped_column(String(512), default="")
    output: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    reasoning: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(16), default="pending")
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    tokens: Mapped[int] = mapped_column(Integer, default=0)
    # condition 步专用：flag 读取键 / 为真时跳过的后续 step idx 列表
    flag_key: Mapped[str | None] = mapped_column(String(64), nullable=True)
    skip_if_true: Mapped[bool] = mapped_column(Boolean, default=True)
    skip_targets: Mapped[list | None] = mapped_column(JSON, nullable=True)


class Approval(Base):
    __tablename__ = "approval"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    run_id: Mapped[str] = mapped_column(ForeignKey("run.id"), index=True, nullable=False)
    step_id: Mapped[str] = mapped_column(ForeignKey("step.id"), nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    risk_note: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(16), default="pending", index=True)  # pending|approved|rejected
    decided_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    note: Mapped[str] = mapped_column(Text, default="")


class Usage(Base):
    __tablename__ = "usage"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    employee_id: Mapped[str | None] = mapped_column(ForeignKey("employee.id"), nullable=True)  # NULL=supervisor
    model: Mapped[str] = mapped_column(String(128), default="")
    tokens_in: Mapped[int] = mapped_column(Integer, default=0)
    tokens_out: Mapped[int] = mapped_column(Integer, default=0)
    cost_est: Mapped[float] = mapped_column(Float, default=0.0)
