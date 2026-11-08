"""RAG（PLAN §8，M1 轻量化实现）：SQLite 存向量 + numpy 余弦，零重依赖离线可用。

嵌入策略：
- 默认（离线）：字符 n-gram（bigram+trigram）哈希到 256 维并归一化 —— 确定性、无依赖
- 可选：pip install -e ".[embeddings]" 且 TEAMDESK_EMBED=bge 时用 bge-small-zh（维度不一致的旧向量会被跳过）
"""
from __future__ import annotations

import hashlib
import os

import numpy as np

from .db import SessionLocal
from .models import Chunk  # noqa: F401  (供类型标注复用)

HASH_DIM = 256
CHUNK_SIZE = 400
CHUNK_OVERLAP = 80  # 滑窗步长 = 400 - 80


# ---------- 嵌入 ----------

def _hash_embed(text: str) -> np.ndarray:
    v = np.zeros(HASH_DIM, dtype=np.float32)
    t = text.lower()
    pad = f"\u0001{t}\u0002"
    grams = [pad[i:i + 2] for i in range(len(pad) - 1)] + [pad[i:i + 3] for i in range(len(pad) - 2)]
    for g in grams:
        h = int(hashlib.md5(g.encode("utf-8")).hexdigest()[:8], 16)
        idx = h % HASH_DIM
        sign = 1.0 if (h >> 31) & 1 else -1.0
        v[idx] += sign
    n = float(np.linalg.norm(v))
    return v / n if n > 0 else v


class _BGEEmbedder:
    _model = None

    def __call__(self, text: str) -> np.ndarray:
        if _BGEEmbedder._model is None:
            from sentence_transformers import SentenceTransformer
            _BGEEmbedder._model = SentenceTransformer("BAAI/bge-small-zh-v1.5")
        vec = _BGEEmbedder._model.encode([text], normalize_embeddings=True)[0]
        return vec.astype(np.float32)


def get_embedder():
    if os.environ.get("TEAMDESK_EMBED", "").strip().lower() == "bge":
        try:
            import sentence_transformers  # noqa: F401
            return _BGEEmbedder()
        except Exception:
            pass  # 装不上/模型缺失时静默回退哈希嵌入
    return _hash_embed


EMBEDDER = get_embedder()
EMBED_MODE: str = "bge-small-zh" if type(EMBEDDER).__name__ == "_BGEEmbedder" else "hash256"


# ---------- 序列化 ----------

def _pack(vec: np.ndarray) -> str:
    return np.asarray(vec, dtype=np.float32).tobytes().hex()


def _unpack(hexstr: str) -> np.ndarray | None:
    try:
        return np.frombuffer(bytes.fromhex(hexstr), dtype=np.float32)
    except Exception:
        return None


# ---------- 切块 ----------

def chunk_text(text: str) -> list[str]:
    text = (text or "").strip()
    if not text:
        return []
    if len(text) <= CHUNK_SIZE:
        return [text]
    parts = []
    step = CHUNK_SIZE - CHUNK_OVERLAP
    for i in range(0, len(text), step):
        seg = text[i:i + CHUNK_SIZE]
        if seg.strip():
            parts.append(seg)
        if i + CHUNK_SIZE >= len(text):
            break
    return parts


# ---------- Store ----------

class RAGStore:
    async def index_text(self, doc_id: str, text: str) -> int:
        """把文档文本切块+嵌入入库，返回 chunk 数。"""
        from .models import Chunk as C  # 避免循环导入噪音

        pieces = chunk_text(text)
        async with SessionLocal() as s:
            # 幂等：同 doc 先清旧块
            old = await s.execute(C.__table__.select().where(C.doc_id == doc_id))
            for row in old.fetchall():
                await s.execute(C.__table__.delete().where(C.id == row.id))
            for seq, piece in enumerate(pieces):
                s.add(C(doc_id=doc_id, seq=seq, content=piece,
                        embedding_ref=_pack(EMBEDDER(piece))))
            await s.commit()
        return len(pieces)

    async def search(self, query: str, top_k: int = 5, doc_id: str | None = None) -> list[dict]:
        """top_k 余弦相似检索。返回 [{chunk_id, doc_id, doc_name, seq, content, score}]"""
        from .models import Chunk as C, Document as D
        from sqlalchemy import select

        qv = EMBEDDER(query)
        async with SessionLocal() as s:
            stmt = select(C, D.filename).join(D, C.doc_id == D.id)
            if doc_id:
                stmt = stmt.where(C.doc_id == doc_id)
            rows = (await s.execute(stmt)).all()

        scored = []
        for chunk, doc_name in rows:
            vec = _unpack(chunk.embedding_ref)
            if vec is None or vec.shape != qv.shape:
                continue
            score = float(np.dot(vec, qv))
            scored.append({
                "chunk_id": chunk.id, "doc_id": chunk.doc_id, "doc_name": doc_name,
                "seq": chunk.seq, "content": chunk.content, "score": round(score, 4),
            })
        scored.sort(key=lambda x: x["score"], reverse=True)
        return scored[:top_k]


rag = RAGStore()
