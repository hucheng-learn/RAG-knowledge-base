"""文档业务逻辑层：上传、解析、清洗、分块、向量入库的编排入口。

第三阶段全链路：保存 → 解析 → 清洗 → 分块 → MySQL 落库(拿chunk_id)
→ 向量化 → 写 Milvus → 回填 MySQL.vector_id。

双写一致性（6.3）：先 MySQL 落库（拿到 chunk.id 作 Milvus 主键），
再写 Milvus；任一环节失败走 _compensate 补偿（删 Milvus + 删 MySQL + 删文件），
保证两边不残留半成品。CPU 密集/阻塞 IO 全部 run_in_threadpool 防阻塞事件循环。
"""

from dataclasses import dataclass
from pathlib import Path

from fastapi import UploadFile
from starlette.concurrency import run_in_threadpool

from app.config.settings import get_settings
from app.models.orm import get_session
from app.models.orm.chunk import Chunk
from app.models.orm.document import Document
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
from app.utils.file_utils import get_extension, save_upload_file
from app.utils.logger import get_logger

logger = get_logger(__name__)
settings = get_settings()


@dataclass
class _ChunkRecord:
    """入库后的分块记录（含数据库自增 id，用于与 Milvus 关联）。"""

    chunk_id: int
    content: str
    chunk_index: int
    page_number: int


async def upload_document(upload_file: UploadFile) -> UploadResponse:
    """上传文档：保存 → 解析 → 清洗 → 分块 → 落库 → 向量化 → 写 Milvus。"""
    target_path: Path = await save_upload_file(upload_file)
    file_size = target_path.stat().st_size
    doc_id: int | None = None

    try:
        # 解析 + 清洗 + 分块
        extension = get_extension(upload_file.filename or "")
        parser = get_parser(extension)
        parse_result = await run_in_threadpool(parser.parse, target_path)
        cleaned = await run_in_threadpool(clean_text, parse_result.text)
        chunks = await run_in_threadpool(chunk_document, parse_result)

        # 1) MySQL 落库（单事务），拿 doc_id + 每个 chunk 的 id
        doc_id, chunk_records = await run_in_threadpool(
            _persist_document, target_path.stem, upload_file.filename,
            file_size, cleaned, chunks,
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
            await run_in_threadpool(_compensate, doc_id)
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
) -> tuple:
    """documents + chunks 单事务落库，返回 (doc_id, chunk_records)。

    一次性 add_all + flush，所有 chunk 的自增 id 一次填充，避免逐条
    flush 造成的 N 次往返。
    """
    session = get_session()
    try:
        doc = Document(
            file_id=file_id,
            original_filename=original_filename or "",
            file_size=file_size,
            char_count=len(cleaned),
            chunk_count=len(chunks),
        )
        session.add(doc)
        session.flush()  # 拿 doc.id

        chunk_objs = [
            Chunk(
                doc_id=doc.id,
                chunk_index=c.chunk_index,
                content=c.content,
                page_number=c.page_number,
            )
            for c in chunks
        ]
        session.add_all(chunk_objs)
        session.flush()  # 一次性填充所有 chunk.id

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
    """回填 vector_id（= chunk.id，即 Milvus 主键），标记已向量化。"""
    session = get_session()
    try:
        session.query(Chunk).filter(Chunk.doc_id == doc_id).update(
            {Chunk.vector_id: Chunk.id}, synchronize_session=False
        )
        session.commit()
    except Exception:
        session.rollback()
        logger.exception("回填 vector_id 失败: doc_id=%s", doc_id)
        raise
    finally:
        session.close()


def _compensate(doc_id: int) -> None:
    """补偿清理：删 Milvus 向量 + 删 MySQL 记录（幂等，单点失败不阻断）。"""
    try:
        delete_by_doc(doc_id)
    except Exception:
        logger.exception("补偿删除 Milvus 向量失败: doc_id=%s", doc_id)
    session = get_session()
    try:
        session.query(Document).filter(Document.id == doc_id).delete()
        session.commit()
    except Exception:
        session.rollback()
        logger.exception("补偿删除 MySQL 文档失败: doc_id=%s", doc_id)
    finally:
        session.close()
