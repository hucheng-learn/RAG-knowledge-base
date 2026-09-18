"""FastAPI 应用入口。

职责：
1. 创建 FastAPI 实例，注册路由、异常处理器、中间件；
2. lifespan 启动钩子：创建上传/日志目录；
3. 提供 /health 健康检查（供 docker / 负载均衡探活使用）。

全局设施（本模块完成）：
- 统一返回体 {code, msg, data}：app/utils/response.py；
- 全局异常捕获：app/utils/exceptions.py，启动时注册全部处理器；
- 全局日志：app/utils/logger.py，请求日志中间件记录每个请求。
"""

import time
import asyncio
import uuid
from collections import defaultdict, deque
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from starlette.responses import Response

from app.config.settings import get_settings
from app.models.orm import init_db
from app.routers import chat, document, knowledge_base
from app.utils.exceptions import register_exception_handlers
from app.utils.logger import get_logger, setup_logging
from app.utils.response import json_fail, success
from app.service.document_worker import run_document_worker

# 模块顶部初始化日志（先于一切业务日志，保证启动期日志也能落盘）
setup_logging()
logger = get_logger(__name__)
settings = get_settings()
_rate_limit_buckets: dict[str, deque[float]] = defaultdict(deque)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    """应用生命周期钩子：启动时初始化，关闭时清理。"""
    # 启动：确保上传目录、日志目录存在（目录不存在时文件写入会报错）
    settings.ensure_dirs()
    # 初始化 MySQL：建库 + 建表。MySQL 不可用时降级启动（打 ERROR 日志，
    # 上传接口会以 500 明确报错），不让单个依赖故障拖垮整个服务
    try:
        init_db()
    except Exception:
        logger.exception("MySQL 初始化失败，上传接口暂不可用")
    stop_event = asyncio.Event()
    worker_task = None
    if settings.document_worker_enabled:
        worker_task = asyncio.create_task(run_document_worker(stop_event), name="document-worker")
        logger.info("文档 worker 已启动")
    logger.info("应用启动完成: %s v%s", settings.app_name, settings.app_version)
    yield
    stop_event.set()
    if worker_task is not None:
        await worker_task
    # 关闭：后续如有数据库连接池、向量库客户端，在此处统一释放
    logger.info("应用关闭")

# 创建 FastAPI 实例
app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    debug=settings.debug,
    lifespan=lifespan,
)

# 全局异常处理器：所有异常统一转 {code, msg, data} 返回格式
register_exception_handlers(app)

# 业务路由：文档上传/解析/删除 + 知识库管理 + RAG 问答
app.include_router(document.router)
app.include_router(knowledge_base.router)
app.include_router(chat.router)


@app.middleware("http")
async def request_log_middleware(request: Request, call_next) -> Response:
    """请求日志中间件：记录方法、路径、状态码、耗时。

    异常时打印完整堆栈后重新抛出（交给全局异常处理器转统一响应）。
    """
    start = time.perf_counter()
    trace_id = request.headers.get("X-Trace-Id") or uuid.uuid4().hex
    request.state.trace_id = trace_id
    if request.url.path.startswith("/api/"):
        now = time.monotonic()
        client_key = request.client.host if request.client else "unknown"
        bucket = _rate_limit_buckets[client_key]
        cutoff = now - settings.rate_limit_window_seconds
        while bucket and bucket[0] <= cutoff:
            bucket.popleft()
        if len(bucket) >= settings.rate_limit_requests:
            logger.warning("请求限流: trace_id=%s client=%s path=%s", trace_id, client_key, request.url.path)
            response = json_fail(429, "请求过于频繁，请稍后重试", status_code=429)
            response.headers["X-Trace-Id"] = trace_id
            return response
        bucket.append(now)
    try:
        response = await call_next(request)
    except Exception:
        logger.exception("请求处理异常: %s %s", request.method, request.url.path)
        raise
    cost_ms = (time.perf_counter() - start) * 1000
    logger.info(
        "请求: trace_id=%s %s %s -> %d (%.1fms)",
        trace_id, request.method, request.url.path, response.status_code, cost_ms,
    )
    response.headers["X-Trace-Id"] = trace_id
    return response


@app.get("/health", tags=["system"], summary="健康检查")
async def health_check() -> dict:
    """健康检查接口：探活用，返回服务基本信息（统一返回格式）。"""
    return success(
        data={"status": "ok", "app": settings.app_name, "version": settings.app_version},
    )


# 极简前端：必须挂在所有路由之后（Starlette 按注册顺序匹配，
# 放最后才不会遮蔽 /health、/api/v1/*、/docs 等已注册路由）
app.mount(
    "/",
    StaticFiles(directory=Path(__file__).resolve().parent / "static", html=True),
    name="frontend",
)
