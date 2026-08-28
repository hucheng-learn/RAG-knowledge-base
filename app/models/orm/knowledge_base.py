"""知识库 ORM 模型（与数据库实际表结构一致）。

说明：本表最初按完整设计手动建表（比基础版多了 owner_id / 每库分块配置 /
doc_count / status 等字段），以实际数据库为准补齐。
"""

from datetime import datetime
from typing import List, Optional

from sqlalchemy import DateTime, Integer, String, func
from sqlalchemy.dialects.mysql import TINYINT
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.orm import Base


class KnowledgeBase(Base):
    """知识库：文档的顶层容器（对应一个文件夹）。"""

    __tablename__ = "knowledge_bases"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(
        String(64), unique=True, nullable=False, comment="知识库名称",
    )
    description: Mapped[Optional[str]] = mapped_column(String(255), comment="描述")
    owner_id: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True, index=True, comment="所属用户ID",
    )
    embedding_model: Mapped[Optional[str]] = mapped_column(
        String(64), comment="嵌入模型名称",
    )
    chunk_strategy: Mapped[Optional[str]] = mapped_column(
        String(32), comment="分块策略(fixed/semantic/sentence)",
    )
    chunk_size: Mapped[Optional[int]] = mapped_column(
        Integer, comment="分块大小(字符数)",
    )
    chunk_overlap: Mapped[Optional[int]] = mapped_column(
        Integer, comment="分块重叠(字符数)",
    )
    doc_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, comment="文档数量",
    )
    status: Mapped[int] = mapped_column(
        TINYINT, nullable=False, default=1, comment="状态: 0-禁用 1-启用",
    )
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime, comment="更新时间")
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), comment="创建时间",
    )

    # 关系：一个知识库包含多个文档
    documents: Mapped[List["Document"]] = relationship(  # noqa: F821
        back_populates="knowledge_base", cascade="all, delete-orphan",
    )
