"""文档上传/列表/详情：解析 → document + chunk + embed（PLAN §6/§8）。"""
from __future__ import annotations

import io
import os

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..bus import bus
from ..config import config
from ..db import SessionLocal, get_session
from ..models import Chunk, Document
from ..rag import rag

router = APIRouter(tags=["documents"])

_KIND_BY_EXT = {".xlsx": "xlsx", ".csv": "csv", ".pdf": "pdf", ".txt": "txt", ".md": "md"}
_MAX_BYTES = 20 * 1024 * 1024  # 20MB


async def _extract(content: bytes, ext: str) -> tuple[str, int | None]:
    """返回 (text, rows)。"""
    kind = _KIND_BY_EXT[ext]
    if kind == "xlsx":
        import pandas as pd
        df = pd.read_excel(io.BytesIO(content))
        return df.to_csv(index=False), int(len(df))
    if kind == "csv":
        import pandas as pd
        df = pd.read_csv(io.BytesIO(content))
        return df.to_csv(index=False), int(len(df))
    if kind == "pdf":
        from pypdf import PdfReader
        reader = PdfReader(io.BytesIO(content))
        return "\n\n".join((p.extract_text() or "") for p in reader.pages), None
    # txt / md
    for enc in ("utf-8", "gb18030"):
        try:
            return content.decode(enc), None
        except UnicodeDecodeError:
            continue
    raise HTTPException(415, "文本编码无法识别")


async def index_document(doc_id: str, filename: str, content: bytes) -> tuple[Document, int]:
    """公共入库流程（上传与启动时 corpus 索引共用）。"""
    ext = os.path.splitext(filename)[1].lower()
    if ext not in _KIND_BY_EXT:
        raise HTTPException(415, f"不支持的文件类型: {ext}")
    text, rows = await _extract(content, ext)
    async with SessionLocal() as s:
        doc = Document(filename=filename, kind=_KIND_BY_EXT[ext], size=len(content),
                       rows=rows, text_preview=(text or "")[:400])
        s.add(doc)
        await s.commit()
        await s.refresh(doc)
    n_chunks = await rag.index_text(doc.id, text)
    async with SessionLocal() as s:
        doc = await s.get(Document, doc.id)
        doc.indexed = True
        await s.commit()
    bus.publish("doc.indexed", payload={"doc_id": doc.id, "filename": filename,
                                        "chunks": n_chunks, "rows": rows})
    return doc, n_chunks


@router.post("/api/documents", status_code=201)
async def upload_document(file: UploadFile):
    content = await file.read()
    if not content:
        raise HTTPException(400, "空文件")
    if len(content) > _MAX_BYTES:
        raise HTTPException(413, "文件超过 20MB")
    try:
        doc, n_chunks = await index_document("", file.filename or "unnamed", content)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(422, f"解析失败: {e}") from e
    return {"doc_id": doc.id, "filename": doc.filename, "kind": doc.kind,
            "rows": doc.rows, "chunks": n_chunks, "indexed": doc.indexed}


@router.get("/api/documents")
async def list_documents(limit: int = 50, session: AsyncSession = Depends(get_session())):
    limit = max(1, min(limit, 200))
    docs = (await session.execute(select(Document).order_by(Document.created_at.desc()).limit(limit))).scalars().all()
    return {"documents": [{
        "id": d.id, "filename": d.filename, "kind": d.kind, "size": d.size,
        "rows": d.rows, "text_preview": d.text_preview[:200], "indexed": d.indexed,
        "created_at": d.created_at.isoformat(),
    } for d in docs]}


@router.get("/api/documents/{doc_id}")
async def get_document(doc_id: str, session: AsyncSession = Depends(get_session())):
    doc = await session.get(Document, doc_id)
    if doc is None:
        raise HTTPException(404, "document 不存在")
    chunks = (await session.execute(
        select(Chunk).where(Chunk.doc_id == doc_id).order_by(Chunk.seq))).scalars().all()
    return {
        "id": doc.id, "filename": doc.filename, "kind": doc.kind, "size": doc.size,
        "rows": doc.rows, "text_preview": doc.text_preview, "indexed": doc.indexed,
        "created_at": doc.created_at.isoformat(),
        "chunks": [{"id": c.id, "seq": c.seq, "content": c.content, "score": c.score}
                   for c in chunks[:200]],
    }


# 启动时预置语料索引（幂等：同名不重复）
async def index_corpus_if_needed() -> int:
    corpus_dir = os.path.join(config.DATA_DIR, "corpus")
    if not os.path.isdir(corpus_dir):
        return 0
    indexed = 0
    for fn in sorted(os.listdir(corpus_dir)):
        ext = os.path.splitext(fn)[1].lower()
        if ext not in (".txt", ".md"):
            continue
        path = os.path.join(corpus_dir, fn)
        with open(path, "rb") as f:
            content = f.read()
        async with SessionLocal() as s:
            exists = (await s.execute(
                select(Document).where(Document.filename == fn))).scalar_one_or_none()
        if exists is not None:
            continue
        try:
            await index_document("", fn, content)
            indexed += 1
        except Exception:
            continue
    return indexed
