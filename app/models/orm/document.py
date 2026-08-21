"""文档 ORM 模型：上传文件的元数据记录。"""

from datetime import datetime
from typing import List, Optional

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.orm import Base


class Document(Base):
    """文档：对应一次成功上传（file_id 即上传接口返回的 uuid）。"""

    __tablename__ = "documents"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    kb_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("knowledge_bases.id"), nullable=True, comment="知识库ID（第四阶段接入）",
    )
    file_id: Mapped[str] = mapped_column(
        String(64), unique=True, nullable=False, comment="上传返回的文件ID（uuid存储名）",
    )
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False, comment="原始文件名")
    file_size: Mapped[int] = mapped_column(BigInteger, nullable=False, comment="文件大小（字节）")
    char_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, comment="清洗后总字符数")
    chunk_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, comment="分块数量")
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), comment="创建时间",
    )

    # 关系：文档的分块记录；删除文档时级联删除全部 chunk（第四阶段）
    chunks: Mapped[List["Chunk"]] = relationship(  # noqa: F821
        back_populates="document", cascade="all, delete-orphan",
    )
    knowledge_base: Mapped[Optional["KnowledgeBase"]] = relationship(  # noqa: F821
        back_populates="documents",
    )
