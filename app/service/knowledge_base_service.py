"""知识库业务逻辑：新建/查询/删除；删除时级联清理文档全部分层数据。

设计要点（面试点）：
1. name 唯一：新建时先查重，重复抛业务异常；
2. 删除知识库 = 遍历其下所有文档 → 逐个 purge_document（级联清理
   Milvus 向量 + MySQL chunks/documents + 磁盘文件）→ 再删知识库行；
3. 级联顺序：先删子表（chunks）再删父表（documents/知识库）——
   SQLAlchemy 批量 Query.delete() 不触发 ORM 关系级联，必须显式排序。
"""

from app.models.orm import get_session
from app.models.orm.document import Document
from app.models.orm.knowledge_base import KnowledgeBase
from app.models.schemas import (
    DocumentBrief,
    KnowledgeBaseDetail,
    KnowledgeBaseSummary,
)
from app.service.document_service import purge_document
from app.utils.exceptions import BizException
from app.utils.logger import get_logger
from app.utils.response import RespCode

logger = get_logger(__name__)


def create_kb(name: str, description: str | None = None) -> KnowledgeBaseSummary:
    """新建知识库，name 唯一，重复抛业务异常。"""
    session = get_session()
    try:
        exists = session.query(KnowledgeBase).filter(KnowledgeBase.name == name).first()
        if exists:
            raise BizException(f"知识库已存在: {name}")
        kb = KnowledgeBase(name=name, description=description)
        session.add(kb)
        session.commit()
        session.refresh(kb)  # 刷新 server_default 的 created_at
        logger.info("知识库已创建: id=%s name=%s", kb.id, kb.name)
        return KnowledgeBaseSummary(
            id=kb.id, name=kb.name, description=kb.description,
            doc_count=0, created_at=kb.created_at,
        )
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def list_kbs() -> list:
    """查询全部知识库（doc_count 取自维护好的冗余列，上传/删除时同步更新）。"""
    session = get_session()
    try:
        kbs = session.query(KnowledgeBase).order_by(KnowledgeBase.id).all()
        return [
            KnowledgeBaseSummary(
                id=kb.id, name=kb.name, description=kb.description,
                doc_count=kb.doc_count, created_at=kb.created_at,
            )
            for kb in kbs
        ]
    finally:
        session.close()


def get_kb(kb_id: int) -> KnowledgeBaseDetail:
    """查询单个知识库详情（含文档列表）。"""
    session = get_session()
    try:
        kb = session.query(KnowledgeBase).filter(KnowledgeBase.id == kb_id).first()
        if kb is None:
            raise BizException(f"知识库不存在: kb_id={kb_id}", code=RespCode.NOT_FOUND)
        docs = (
            session.query(Document)
            .filter(Document.kb_id == kb_id)
            .order_by(Document.id)
            .all()
        )
        return KnowledgeBaseDetail(
            id=kb.id, name=kb.name, description=kb.description,
            created_at=kb.created_at,
            documents=[_to_doc_brief(d) for d in docs],
        )
    finally:
        session.close()


def delete_kb(kb_id: int) -> dict:
    """删除知识库，级联清理其下所有文档（Milvus + MySQL + 文件）。

    Returns:
        {"deleted": True, "kb_id": ..., "name": ..., "deleted_documents": N}
    """
    session = get_session()
    try:
        kb = session.query(KnowledgeBase).filter(KnowledgeBase.id == kb_id).first()
        if kb is None:
            raise BizException(f"知识库不存在: kb_id={kb_id}", code=RespCode.NOT_FOUND)
        name = kb.name
        docs = session.query(Document).filter(Document.kb_id == kb_id).all()
        for doc in docs:
            purge_document(doc)  # 各自独立 session，逐文档级联清理
        session.query(KnowledgeBase).filter(KnowledgeBase.id == kb_id).delete()
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
    logger.info("知识库已删除: id=%s name=%s 级联文档=%d", kb_id, name, len(docs))
    return {
        "deleted": True, "kb_id": kb_id, "name": name,
        "deleted_documents": len(docs),
    }


def _to_doc_brief(doc) -> DocumentBrief:
    """Document ORM → DocumentBrief 响应模型。"""
    return DocumentBrief(
        file_id=doc.file_id,
        original_filename=doc.original_filename,
        file_size=doc.file_size,
        char_count=doc.char_count,
        chunk_count=doc.chunk_count,
        created_at=doc.created_at,
    )
