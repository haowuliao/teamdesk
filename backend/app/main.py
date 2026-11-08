"""TeamDesk backend 入口：装配 + 启动钩子（建表/seed/corpus 索引/断点恢复）。"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api import approvals, documents, employees, runs, sse, tasks, usage
from .bus import bus
from .config import config
from .db import dispose_db, init_db
from .employees.seed import seed_employees
from .llm import llm
from .rag import EMBED_MODE
from .sop.engine import recover

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("teamdesk.main")


@asynccontextmanager
async def lifespan(_: FastAPI):
    await init_db()
    n_emp = await seed_employees()
    n_corpus = await documents.index_corpus_if_needed()
    await recover()
    log.info("启动完成: employees_seeded=%s corpus_indexed=%s llm_online=%s embed=%s",
             n_emp, n_corpus, llm.online, EMBED_MODE)
    yield
    await dispose_db()


app = FastAPI(title="TeamDesk 数字班组工作台", version="0.1.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=False,
                   allow_methods=["*"], allow_headers=["*"])

for r in (sse.router, employees.router, runs.router, tasks.router,
          documents.router, approvals.router, usage.router):
    app.include_router(r)


@app.get("/api/health")
async def health():
    return {"ok": True, "llm_online": llm.online, "model": llm.model,
            "embed_mode": EMBED_MODE, "offline_mode": not llm.online}
