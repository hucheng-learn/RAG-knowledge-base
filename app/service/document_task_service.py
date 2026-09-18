"""异步文档任务的领取、完成、失败和超时回收。"""

from datetime import datetime, timedelta

from sqlalchemy import or_

from app.models.orm import get_session
from app.models.orm.document import Document, DocumentStatus
from app.models.orm.document_task import DocumentTask, DocumentTaskStatus
from app.utils.logger import get_logger

logger = get_logger(__name__)


def enqueue_document_task(doc_id: int, *, max_attempts: int = 3) -> int:
    """为文档创建任务并返回 task_id；doc_id 唯一防止重复入队。"""
    if max_attempts < 1:
        raise ValueError("max_attempts 必须大于等于 1")
    session = get_session()
    try:
        existing = session.query(DocumentTask).filter(DocumentTask.doc_id == doc_id).first()
        if existing is not None:
            return existing.id
        task = DocumentTask(
            doc_id=doc_id,
            status=DocumentTaskStatus.PENDING,
            max_attempts=max_attempts,
            next_run_at=datetime.now(),
        )
        session.add(task)
        session.commit()
        logger.info("文档任务已入队: task_id=%s doc_id=%s", task.id, doc_id)
        return task.id
    except Exception:
        session.rollback()
        logger.exception("文档任务入队失败: doc_id=%s", doc_id)
        raise
    finally:
        session.close()


def claim_next_task(
    *, worker_timeout_seconds: int = 900,
) -> DocumentTask | None:
    """领取一个可执行任务；同一数据库事务内完成超时回收和加锁。

    MySQL 8 使用 ``FOR UPDATE SKIP LOCKED``，多个 worker 并发时不会领取同一行。
    旧版本或测试数据库不支持时，事务锁仍保证单进程/低并发场景正确。
    """
    if worker_timeout_seconds < 1:
        raise ValueError("worker_timeout_seconds 必须大于等于 1")
    session = get_session()
    now = datetime.now()
    stale_at = now - timedelta(seconds=worker_timeout_seconds)
    try:
        query = (
            session.query(DocumentTask)
            .filter(
                or_(
                    (DocumentTask.status == DocumentTaskStatus.PENDING)
                    & (DocumentTask.next_run_at <= now),
                    (DocumentTask.status == DocumentTaskStatus.PROCESSING)
                    & (DocumentTask.locked_at < stale_at),
                )
            )
            .order_by(DocumentTask.next_run_at.asc(), DocumentTask.id.asc())
        )
        try:
            task = query.with_for_update(skip_locked=True).first()
        except Exception:
            # MariaDB/旧 MySQL 或 SQLite 测试环境可能不接受 skip_locked。
            session.rollback()
            task = query.with_for_update().first()
        if task is None:
            session.rollback()
            return None
        task.status = DocumentTaskStatus.PROCESSING
        task.attempts += 1
        task.locked_at = now
        task.updated_at = now
        session.commit()
        session.expunge(task)
        logger.info("领取文档任务: task_id=%s doc_id=%s attempt=%s", task.id, task.doc_id, task.attempts)
        return task
    except Exception:
        session.rollback()
        logger.exception("领取文档任务失败")
        raise
    finally:
        session.close()


def mark_task_succeeded(task_id: int) -> None:
    """将任务标记为成功，清除锁和历史错误。"""
    _update_task(task_id, status=DocumentTaskStatus.SUCCEEDED, locked_at=None, last_error=None)


def mark_task_failed(task_id: int, error: str, *, retry_delay_seconds: int = 30) -> None:
    """记录失败；仍有重试次数时重新排队，否则进入终态失败。"""
    if retry_delay_seconds < 0:
        raise ValueError("retry_delay_seconds 不能小于 0")
    session = get_session()
    try:
        task = session.query(DocumentTask).filter(DocumentTask.id == task_id).first()
        if task is None:
            logger.warning("标记任务失败时任务不存在: task_id=%s", task_id)
            return
        now = datetime.now()
        can_retry = task.attempts < task.max_attempts
        task.status = DocumentTaskStatus.PENDING if can_retry else DocumentTaskStatus.FAILED
        task.next_run_at = now + timedelta(seconds=retry_delay_seconds) if can_retry else now
        task.locked_at = None
        task.last_error = error[:4000]
        task.updated_at = now
        if not can_retry:
            session.query(Document).filter(Document.id == task.doc_id).update(
                {
                    Document.status: DocumentStatus.FAILED,
                    Document.parse_error: error[:4000],
                    Document.updated_at: now,
                },
                synchronize_session=False,
            )
        session.commit()
        logger.warning(
            "文档任务失败: task_id=%s attempt=%s retry=%s error=%s",
            task_id, task.attempts, can_retry, error[:300],
        )
    except Exception:
        session.rollback()
        logger.exception("记录文档任务失败状态异常: task_id=%s", task_id)
        raise
    finally:
        session.close()


def _update_task(task_id: int, **values) -> None:
    session = get_session()
    try:
        task = session.query(DocumentTask).filter(DocumentTask.id == task_id).first()
        if task is None:
            logger.warning("更新任务时任务不存在: task_id=%s", task_id)
            return
        values["updated_at"] = datetime.now()
        for key, value in values.items():
            setattr(task, key, value)
        session.commit()
    except Exception:
        session.rollback()
        logger.exception("更新文档任务失败: task_id=%s", task_id)
        raise
    finally:
        session.close()
