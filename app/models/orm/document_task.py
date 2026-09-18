"""异步文档处理任务 ORM。"""

from datetime import datetime
from enum import IntEnum

from sqlalchemy import DateTime, ForeignKey, Integer, Text, func
from sqlalchemy.dialects.mysql import TINYINT
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.orm import Base


class DocumentTaskStatus(IntEnum):
    """任务生命周期状态。"""

    PENDING = 0
    PROCESSING = 1
    SUCCEEDED = 2
    FAILED = 3


class DocumentTask(Base):
    """文档异步处理任务：持久化 worker 的领取、重试和失败信息。"""

    __tablename__ = "document_tasks"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    doc_id: Mapped[int] = mapped_column(
        ForeignKey("documents.id"), unique=True, nullable=False, comment="文档ID",
    )
    status: Mapped[int] = mapped_column(
        TINYINT, nullable=False, default=DocumentTaskStatus.PENDING, index=True,
        comment="任务状态: 0-待处理 1-处理中 2-成功 3-失败",
    )
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0, comment="已尝试次数")
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=3, comment="最大尝试次数")
    next_run_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(), index=True, comment="下次执行时间",
    )
    locked_at: Mapped[datetime | None] = mapped_column(DateTime, comment="领取时间")
    last_error: Mapped[str | None] = mapped_column(Text, comment="最近一次错误")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime | None] = mapped_column(DateTime)

    document = relationship("Document", backref="task", uselist=False)
