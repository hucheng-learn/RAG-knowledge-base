"""后台文档任务 worker。"""

import asyncio

from app.config.settings import get_settings
from app.service.document_service import process_document_task
from app.service.document_task_service import claim_next_task
from app.utils.logger import get_logger

logger = get_logger(__name__)


async def run_document_worker(stop_event: asyncio.Event) -> None:
    """持续领取任务；同步解析/向量化放在线程池，避免阻塞事件循环。"""
    settings = get_settings()
    while not stop_event.is_set():
        task = await asyncio.to_thread(
            claim_next_task, worker_timeout_seconds=settings.document_worker_timeout_seconds,
        )
        if task is not None:
            await asyncio.to_thread(process_document_task, task.id)
            continue
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=settings.document_worker_poll_seconds)
        except asyncio.TimeoutError:
            pass
    logger.info("文档 worker 已停止")
