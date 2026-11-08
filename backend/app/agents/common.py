"""Agent 共享工具（B 工单）：文档全文还原、DataFrame 读取、思考事件发射。

关键点：上传文件不落地磁盘，原始文本只存在于 RAG 切块里（~400 字窗口、步长 320）。
csv/xlsx 入库时整体转成 CSV 文本再切块，所以可以按切块规则无损还原全文。
"""
from __future__ import annotations

import io
import json

from ..db import SessionLocal
from ..rag import CHUNK_OVERLAP


def _thinking(ctx, text: str) -> None:
    """发一条 step.thinking（前端打字机流）；任何失败都不影响主流程。"""
    try:
        emp_id = ctx.employee.get("id") if isinstance(ctx.employee, dict) else None
        ctx.bus.publish("step.thinking", run_id=ctx.run_id, employee_id=emp_id,
                        payload={"step_id": ctx.step_id, "text": text})
    except Exception:
        pass


async def doc_text(doc_id: str) -> tuple[str, str]:
    """从 chunk 表还原文档全文。返回 (text, filename)。"""
    from sqlalchemy import select

    from ..models import Chunk, Document

    async with SessionLocal() as s:
        doc = await s.get(Document, doc_id)
        if doc is None:
            raise RuntimeError(f"document 不存在: {doc_id}")
        rows = (await s.execute(
            select(Chunk).where(Chunk.doc_id == doc_id).order_by(Chunk.seq))).scalars().all()
    if not rows:
        return "", doc.filename
    if len(rows) == 1:
        return rows[0].content, doc.filename
    # 滑窗切块：相邻块重叠 CHUNK_OVERLAP 字，拼接时只去重叠部分
    parts = [rows[0].content]
    for r in rows[1:]:
        parts.append(r.content[CHUNK_OVERLAP:] if len(r.content) > CHUNK_OVERLAP else r.content)
    return "".join(parts), doc.filename


async def doc_dataframe(doc_id: str):
    """还原 csv 文本 → pandas.DataFrame（xlsx/csv 入库时都是 CSV 文本）。"""
    import pandas as pd

    text, _ = await doc_text(doc_id)
    return pd.read_csv(io.StringIO(text))


def _pick(df, *patterns) -> str | None:
    """列名模糊匹配（大小写不敏感，子串即中）。"""
    cols = {str(c).lower(): c for c in df.columns}
    for pat in patterns:
        for low, orig in cols.items():
            if pat in low:
                return orig
    return None


def to_jsonable(obj):
    """numpy/pandas 标量 → 原生 JSON 类型（step.output 落库要 JSON 可序列化）。"""
    if isinstance(obj, dict):
        return {k: to_jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [to_jsonable(v) for v in obj]
    try:
        import numpy as np
        if isinstance(obj, np.integer):
            return int(obj)
        if isinstance(obj, np.floating):
            return round(float(obj), 4)
        if isinstance(obj, np.ndarray):
            return [to_jsonable(v) for v in obj.tolist()]
    except Exception:
        pass
    if isinstance(obj, float):
        return round(obj, 4)
    return obj


def clamp_str(s: str, n: int = 200) -> str:
    s = str(s).strip().replace("\n", " ")
    return s if len(s) <= n else s[: n - 1] + "…"


def brief(payload_obj) -> str:
    try:
        return clamp_str(json.dumps(payload_obj, ensure_ascii=False), 120)
    except Exception:
        return str(payload_obj)[:120]
