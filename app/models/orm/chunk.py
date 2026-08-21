"""分块 ORM 模型：检索的最小单元，与 Milvus 向量一一对应。"""

from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.orm import Base


class Chunk(Base):
    """文本分块：content 存原文，vector_id 第三阶段写入 Milvus 向量 id。"""

    __tablename__ = "chunks"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    doc_id: Mapped[int] = mapped_column(
        ForeignKey("documents.id"), nullable=False, index=True, comment="所属文档ID",
    )
    kb_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("knowledge_bases.id"), nullable=True, comment="知识库ID（第四阶段接入）",
    )
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False, comment="文档内块编号（从0开始）")
    content: Mapped[str] = mapped_column(Text, nullable=False, comment="块原始文本")
    page_number: Mapped[int] = mapped_column(Integer, nullable=False, comment="来源页码（从1开始）")
    vector_id: Mapped[Optional[str]] = mapped_column(
        String(64), nullable=True, comment="Milvus向量ID（第三阶段填充，此前为NULL）",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), index=True, comment="创建时间",
    )

    document: Mapped["Document"] = relationship(back_populates="chunks")  # noqa: F821
