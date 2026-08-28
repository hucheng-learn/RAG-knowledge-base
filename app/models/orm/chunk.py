"""分块 ORM 模型（与数据库实际表结构一致）。

说明：实际表比基础版多了 token_count / embedding_status，反映最初设计的
嵌入状态跟踪（0-待嵌入 1-已嵌入 2-失败），以实际数据库为准补齐。
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.mysql import TINYINT
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.orm import Base


class Chunk(Base):
    """文本分块：检索和嵌入的最小单元，与 Milvus 向量一一对应。"""

    __tablename__ = "chunks"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    doc_id: Mapped[int] = mapped_column(
        ForeignKey("documents.id"), nullable=False, index=True, comment="所属文档ID",
    )
    kb_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("knowledge_bases.id"), nullable=True, index=True, comment="知识库ID",
    )
    chunk_index: Mapped[int] = mapped_column(
        Integer, nullable=False, comment="文档内块编号（从0开始）",
    )
    content: Mapped[str] = mapped_column(Text, nullable=False, comment="块原始文本")
    token_count: Mapped[Optional[int]] = mapped_column(Integer, comment="token数量")
    embedding_status: Mapped[int] = mapped_column(
        TINYINT, nullable=False, default=0, index=True,
        comment="嵌入状态: 0-待嵌入 1-已嵌入 2-失败",
    )
    page_number: Mapped[int] = mapped_column(
        Integer, nullable=False, comment="来源页码（从1开始）",
    )
    vector_id: Mapped[Optional[str]] = mapped_column(
        String(64), nullable=True, comment="Milvus向量ID（与chunk id一一对应）",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), index=True, comment="创建时间",
    )

    document: Mapped["Document"] = relationship(back_populates="chunks")  # noqa: F821
