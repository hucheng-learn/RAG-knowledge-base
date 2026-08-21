"""知识库 ORM 模型（第四阶段起启用，表结构先行）。"""

from datetime import datetime
from typing import List, Optional

from sqlalchemy import DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.orm import Base


class KnowledgeBase(Base):
    """知识库：文档的归属容器，第四阶段提供增删查接口。"""

    __tablename__ = "knowledge_bases"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, comment="知识库名称")
    description: Mapped[Optional[str]] = mapped_column(String(255), comment="描述")
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), comment="创建时间",
    )

    # 关系：一个知识库包含多个文档（cascade 删除联动，第四阶段删除知识库时用）
    documents: Mapped[List["Document"]] = relationship(  # noqa: F821
        back_populates="knowledge_base", cascade="all, delete-orphan",
    )
