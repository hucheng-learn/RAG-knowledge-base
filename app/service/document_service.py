"""文档业务逻辑层：上传、解析、清洗、分块、向量入库的编排入口。

第三阶段全链路：保存 → 解析 → 清洗 → 分块 → MySQL 落库(拿chunk_id)
→ 向量化 → 写 Milvus → 回填 MySQL.vector_id。

双写一致性（6.3）：先 MySQL 落库（拿到 chunk.id 作 Milvus 主键），
再写 Milvus；任一环节失败走 _compensate 补偿（删 Milvus + 删 MySQL + 删文件），
保证两边不残留半成品。CPU 密集/阻塞 IO 全部 run_in_threadpool 防阻塞事件循环。
"""

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from fastapi import UploadFile
from sqlalchemy import func
from starlette.concurrency import run_in_threadpool

from app.config.settings import get_settings
from app.models.orm import get_session
from app.models.orm.chunk import Chunk
from app.models.orm.document import Document
from app.models.orm.knowledge_base import KnowledgeBase
from app.models.schemas import UploadResponse
from app.service.chunk_service import chunk_document
from app.service.embedding_service import get_embedding_service
from app.service.parser import get_parser
from app.service.vector_service import (
    delete_by_doc,
    ensure_collection,
    insert_chunk_vectors,
)
from app.utils.clean_text import clean_text
from app.utils.exceptions import BizException
from app.utils.file_utils import get_extension, save_upload_file
from app.utils.logger import get_logger
from app.utils.response import RespCode

logger = get_logger(__name__)
settings = get_settings()


@dataclass
class _ChunkRecord:
    """入库后的分块记录（含数据库自增 id，用于与 Milvus 关联）。"""

    chunk_id: int
    content: str
    chunk_index: int
    page_number: int


async def upload_document(
    upload_file: UploadFile, kb_id: int | None = None,
) -> UploadResponse:
    """上传文档：保存 → 解析 → 清洗 → 分块 → 落库 → 向量化 → 写 Milvus。

    Args:
        kb_id: 可选，指定所属知识库；为 None 时文档不归属任何知识库。
    """
    target_path: Path = await save_upload_file(upload_file)
    file_size = target_path.stat().st_size
    doc_id: int | None = None

    try:
        # 若指定知识库，先校验存在（不存在抛业务异常）
        if kb_id is not None:
            await run_in_threadpool(_validate_kb, kb_id)

        # 解析 + 清洗 + 分块
        extension = get_extension(upload_file.filename or "")
        parser = get_parser(extension)
        parse_result = await run_in_threadpool(parser.parse, target_path)
        cleaned = await run_in_threadpool(clean_text, parse_result.text)
        chunks = await run_in_threadpool(chunk_document, parse_result)

        # 1) MySQL 落库（单事务），拿 doc_id + 每个 chunk 的 id
        doc_id, chunk_records = await run_in_threadpool(
            _persist_document, target_path.stem, upload_file.filename,
            file_size, cleaned, chunks, kb_id,
        )

        # 2) 向量化（首次调用会懒加载 bge-m3 模型，较慢）
        vectors = await run_in_threadpool(
            _embed_chunks, [r.content for r in chunk_records],
        )

        # 3) 确保 collection 存在并写 Milvus（vector 主键 = chunk.id）
        await run_in_threadpool(ensure_collection)
        milvus_records = [
            {
                "id": r.chunk_id,
                "vector": vec,
                "doc_id": doc_id,
                "chunk_index": r.chunk_index,
                "page_number": r.page_number,
            }
            for r, vec in zip(chunk_records, vectors)
        ]
        await run_in_threadpool(insert_chunk_vectors, milvus_records)

        # 4) 回填 MySQL chunks.vector_id（标记该块已向量化）
        await run_in_threadpool(_mark_vectorized, doc_id)
    except Exception:
        # 补偿：删 Milvus 向量 + 删 MySQL 记录 + 删文件
        if doc_id is not None:
            await run_in_threadpool(_compensate, doc_id, kb_id)
        target_path.unlink(missing_ok=True)
        logger.warning("文档处理失败已清理: %s doc_id=%s", target_path.name, doc_id)
        raise

    # 预览片段
    preview = cleaned[: settings.preview_max_chars]
    if len(cleaned) > settings.preview_max_chars:
        preview += "..."

    logger.info(
        "文档入库完成: 数据库id=%s file_id=%s 文件名=%s 页数=%d "
        "字符数=%d 分块数=%d 大小=%d字节",
        doc_id, target_path.stem, upload_file.filename,
        len(parse_result.page_texts), len(cleaned), len(chunks), file_size,
    )
    return UploadResponse(
        file_id=target_path.stem,
        original_filename=upload_file.filename or "",
        file_size=file_size,
        preview=preview,
        char_count=len(cleaned),
        chunk_count=len(chunks),
    )


def _embed_chunks(texts: list) -> list:
    """批量向量化（惰性加载模型单例）。"""
    svc = get_embedding_service()
    return svc.embed_texts(texts)


def _persist_document(
    file_id: str,
    original_filename: str,
    file_size: int,
    cleaned: str,
    chunks: list,
    kb_id: int | None = None,
) -> tuple:
    """documents + chunks 单事务落库，返回 (doc_id, chunk_records)。

    一次性 add_all + flush，所有 chunk 的自增 id 一次填充，避免逐条
    flush 造成的 N 次往返。同步管线落库即解析完成（status=2）。
    若挂知识库，同一事务内维护 knowledge_bases.doc_count 冗余计数。
    """
    session = get_session()
    try:
        # 从原始文件名推导文件类型（如 .txt -> txt）
        ext = get_extension(original_filename or "")
        file_type = ext.lstrip(".") or None
        now = datetime.now()
        doc = Document(
            file_id=file_id,
            kb_id=kb_id,
            original_filename=original_filename or "",
            file_type=file_type,
            file_size=file_size,
            char_count=len(cleaned),
            chunk_count=len(chunks),
            status=2,  # 同步管线：解析完成
            updated_at=now,
        )
        session.add(doc)
        session.flush()  # 拿 doc.id

        chunk_objs = [
            Chunk(
                doc_id=doc.id,
                kb_id=kb_id,
                chunk_index=c.chunk_index,
                content=c.content,
                page_number=c.page_number,
            )
            for c in chunks
        ]
        session.add_all(chunk_objs)
        session.flush()  # 一次性填充所有 chunk.id

        # 维护知识库的文档计数（与 list 接口展示一致，同一事务保证原子）
        if kb_id is not None:
            session.query(KnowledgeBase).filter(KnowledgeBase.id == kb_id).update(
                {KnowledgeBase.doc_count: KnowledgeBase.doc_count + 1},
                synchronize_session=False,
            )

        chunk_records = [
            _ChunkRecord(
                chunk_id=obj.id,
                content=c.content,
                chunk_index=c.chunk_index,
                page_number=c.page_number,
            )
            for obj, c in zip(chunk_objs, chunks)
        ]
        session.commit()
        return doc.id, chunk_records
    except Exception:
        session.rollback()
        logger.exception("文档元数据入库失败: file_id=%s", file_id)
        raise
    finally:
        session.close()


def _mark_vectorized(doc_id: int) -> None:
    """回填 vector_id（= chunk.id，即 Milvus 主键）并置 embedding_status=1。"""
    session = get_session()
    try:
        session.query(Chunk).filter(Chunk.doc_id == doc_id).update(
            {Chunk.vector_id: Chunk.id, Chunk.embedding_status: 1},
            synchronize_session=False,
        )
        session.commit()
    except Exception:
        session.rollback()
        logger.exception("回填 vector_id 失败: doc_id=%s", doc_id)
        raise
    finally:
        session.close()


def _compensate(doc_id: int, kb_id: int | None = None) -> None:
    """补偿清理：删 Milvus 向量 + 删 MySQL 记录 + 回退知识库文档计数。

    幂等，单点失败不阻断后续清理。
    """
    try:
        delete_by_doc(doc_id)
    except Exception:
        logger.exception("补偿删除 Milvus 向量失败: doc_id=%s", doc_id)
    session = get_session()
    try:
        # 先删 chunks 再删 documents：Query.delete() 是批量 SQL，
        # 不触发 ORM 关系级联，必须先删子表，否则产生孤儿 chunk
        session.query(Chunk).filter(Chunk.doc_id == doc_id).delete()
        session.query(Document).filter(Document.id == doc_id).delete()
        # 回退知识库文档计数（补偿 persist 时那次 +1）
        if kb_id is not None:
            session.query(KnowledgeBase).filter(KnowledgeBase.id == kb_id).update(
                {KnowledgeBase.doc_count: func.greatest(KnowledgeBase.doc_count - 1, 0)},
                synchronize_session=False,
            )
        session.commit()
    except Exception:
        session.rollback()
        logger.exception("补偿删除 MySQL 文档失败: doc_id=%s", doc_id)
    finally:
        session.close()


# ---------------- 第四阶段：知识库归属 + 文档级联删除 ----------------

def _validate_kb(kb_id: int) -> None:
    """校验知识库存在，不存在抛业务异常（code=NOT_FOUND）。"""
    session = get_session()
    try:
        exists = session.query(KnowledgeBase.id).filter(KnowledgeBase.id == kb_id).first()
        if exists is None:
            raise BizException(f"知识库不存在: kb_id={kb_id}", code=RespCode.NOT_FOUND)
    finally:
        session.close()


def _resolve_storage_path(doc) -> Path:
    """根据 file_id + 原始文件名后缀还原磁盘存储路径（uploads/{file_id}{ext}）。"""
    ext = get_extension(doc.original_filename or "")
    return settings.upload_dir_path / f"{doc.file_id}{ext}"


def purge_document(doc) -> None:
    """级联清理单个文档的全部分层数据：Milvus 向量 → MySQL chunks/documents → 磁盘文件。

    Args:
        doc: Document ORM 对象（只需读取其 id/file_id/original_filename 属性）。
    """
    doc_id = doc.id
    # 1) Milvus 向量（删除异步生效，此处保证请求已发出）
    try:
        delete_by_doc(doc_id)
    except Exception:
        logger.exception("删除 Milvus 向量失败: doc_id=%s", doc_id)
    # 2) MySQL 记录（先子表后父表，批量删除不触发 ORM 级联）+ 回退知识库文档计数
    session = get_session()
    try:
        session.query(Chunk).filter(Chunk.doc_id == doc_id).delete()
        session.query(Document).filter(Document.id == doc_id).delete()
        if doc.kb_id is not None:
            session.query(KnowledgeBase).filter(KnowledgeBase.id == doc.kb_id).update(
                {KnowledgeBase.doc_count: func.greatest(KnowledgeBase.doc_count - 1, 0)},
                synchronize_session=False,
            )
        session.commit()
    except Exception:
        session.rollback()
        logger.exception("删除 MySQL 文档记录失败: doc_id=%s", doc_id)
    finally:
        session.close()
    # 3) 磁盘文件
    storage = _resolve_storage_path(doc)
    if storage.exists():
        storage.unlink()
    logger.info("文档已级联清理: doc_id=%s file_id=%s", doc_id, doc.file_id)


def delete_document(file_id: str) -> dict:
    """按 file_id 删除单个文档（级联清理 Milvus + MySQL + 磁盘文件）。

    Returns:
        {"deleted": True, "file_id": ..., "doc_id": ...}
    """
    session = get_session()
    try:
        doc = session.query(Document).filter(Document.file_id == file_id).first()
        if doc is None:
            raise BizException(f"文档不存在: file_id={file_id}", code=RespCode.NOT_FOUND)
        doc_id = doc.id
    finally:
        session.close()
    purge_document(doc)
    return {"deleted": True, "file_id": file_id, "doc_id": doc_id}
