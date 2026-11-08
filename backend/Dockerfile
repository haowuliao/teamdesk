# TeamDesk backend — python:3.11-slim + uv
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# 先装依赖（利用构建缓存）
COPY pyproject.toml uv.lock ./
RUN pip install --no-cache-dir uv==0.7.* \
    && uv sync --frozen --no-dev

# 应用代码
COPY app ./app

# 运行时数据（SQLite 库 / RAG 语料 / 上传文件），compose 里 volume 挂载到宿主机
VOLUME ["/app/data"]
RUN mkdir -p /app/data/corpus

EXPOSE 8320

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s \
    CMD python -c "import urllib.request;urllib.request.urlopen('http://127.0.0.1:8320/api/health')" || exit 1

# 无 LLM_API_KEY 也能跑（离线模式，PLAN §4）
CMD ["uv", "run", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8320"]
