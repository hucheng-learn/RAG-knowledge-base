"""文档 ORM 模型（与数据库实际表结构一致）。

说明：实际表比基础版多了 file_type / status / parse_error / updated_at，
反映最初设计的异步解析状态跟踪，以实际数据库为准补齐。
"""

from datetime import datetime
from typing import List, Optional

from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.mysql import TINYINT
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.orm import Base


class Document(Base):
    """文档：对应一个上传的文件，属于某个知识库。"""

    __tablename__ = "documents"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    kb_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("knowledge_bases.id"), nullable=True, comment="知识库ID",
    )
    file_id: Mapped[str] = mapped_column(
        String(64), unique=True, nullable=False, comment="上传返回的文件ID（uuid存储名）",
    )
    original_filename: Mapped[str] = mapped_column(
        String(255), nullable=False, comment="原始文件名",
    )
    file_type: Mapped[Optional[str]] = mapped_column(
        String(32), index=True, comment="文件类型(pdf/docx/txt/md等)",
    )
    file_size: Mapped[int] = mapped_column(
        BigInteger, nullable=False, comment="文件大小（字节）",
    )
    char_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, comment="清洗后总字符数",
    )
    chunk_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, comment="分块数量",
    )
    status: Mapped[int] = mapped_column(
        TINYINT, nullable=False, default=0, index=True,
        comment="处理状态: 0-待解析 1-解析中 2-解析完成 3-失败",
    )
    parse_error: Mapped[Optional[str]] = mapped_column(Text, comment="解析失败原因")
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), comment="创建时间",
    )
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime, comment="更新时间")

    # 关系：文档的分块记录；删除文档时级联删除全部 chunk
    chunks: Mapped[List["Chunk"]] = relationship(  # noqa: F821
        back_populates="document", cascade="all, delete-orphan",
    )
    knowledge_base: Mapped[Optional["KnowledgeBase"]] = relationship(  # noqa: F821
        back_populates="documents",
    )
