"""文档业务逻辑层：上传、解析、清洗、分块、向量入库的编排入口。

处理流程：保存 → 解析 → 清洗 → 分块 → 写入 MySQL 和 Milvus。
MySQL 与 Milvus 不共享事务，失败时通过补偿清理半成品；CPU 密集和阻塞 I/O
使用 run_in_threadpool 执行，避免阻塞事件循环。
"""

from dataclasses import dataclass
from datetime import datetime
import hashlib
import json
from pathlib import Path

from fastapi import UploadFile
from sqlalchemy import func
from starlette.concurrency import run_in_threadpool

from app.config.settings import get_settings
from app.models.orm import get_session
from app.models.orm.chunk import Chunk
from app.models.orm.document import Document, DocumentStatus
from app.models.orm.document_task import DocumentTask
from app.models.orm.parse_cache import ParseCache
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
from app.utils.file_utils import get_extension, save_upload_file, sha256_file
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
    block_type: str | None
    heading_path: list[str]


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

        # 去重：同一知识库下不允许同名文件（避免重复上传造成向量重复、检索重复）
        if kb_id is not None and upload_file.filename:
            await run_in_threadpool(_check_duplicate, kb_id, upload_file.filename)

        # 解析 + 清洗 + 分块
        extension = get_extension(upload_file.filename or "")
        parser = get_parser(extension)
        parse_result = await run_in_threadpool(parser.parse, target_path)
        cleaned = await run_in_threadpool(clean_text, parse_result.text)
        # 分块也必须使用清洗后的文本，否则向量库会保留解析噪声，
        # 而文档的 preview/char_count 使用的却是另一份文本。
        cleaned_page_texts = await run_in_threadpool(
            lambda: [clean_text(page) for page in parse_result.page_texts]
        )
        cleaned_blocks = await run_in_threadpool(
            lambda: [
                _clean_block(block) for block in parse_result.blocks
            ]
        )
        chunks = await run_in_threadpool(
            chunk_document, parse_result, cleaned_page_texts, cleaned_blocks
        )

        # 解析降级信息（如 MinerU 失败回退 pdfplumber）：记录到 documents.parse_error，
        # 记录实际解析器及降级原因，便于查询处理结果。
        degrade_note = _build_degrade_note(parse_result, upload_file.filename)

        # 1) MySQL 落库（单事务），拿 doc_id + 每个 chunk 的 id
        doc_id, chunk_records = await run_in_threadpool(
            _persist_document, target_path.stem, upload_file.filename,
            file_size, cleaned, chunks, kb_id, degrade_note,
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
        parser_name=parse_result.parser_name,
        degraded=bool(parse_result.metadata.get("degraded")),
    )


def _embed_chunks(texts: list) -> list:
    """批量向量化（惰性加载模型单例）。"""
    svc = get_embedding_service()
    return svc.embed_texts(texts)


def _clean_block(block):
    """清洗结构化块文本，同时保留块级溯源字段。"""
    from dataclasses import replace

    return replace(block, content=clean_text(block.content))


def _build_degrade_note(parse_result, filename: str | None) -> str | None:
    """构造降级说明（记入 documents.parse_error）；未降级返回 None。"""
    meta = parse_result.metadata or {}
    if not meta.get("degraded"):
        return None
    note = (
        f"已降级解析：{meta.get('primary_parser')} 失败，回退 {meta.get('backup_parser')}；"
        f"原因：{meta.get('degrade_reason')}"
    )
    logger.warning("文档解析降级: 文件名=%s %s", filename, note)
    return note


def _safe_json_list(raw: str | None) -> list:
    """把 chunks.heading_path（JSON 数组字符串列）解析成列表；异常或非数组按空列表兜底。"""
    if not raw:
        return []
    try:
        value = json.loads(raw)
    except (TypeError, ValueError):
        return []
    return value if isinstance(value, list) else []


def _persist_document(
    file_id: str,
    original_filename: str,
    file_size: int,
    cleaned: str,
    chunks: list,
    kb_id: int | None = None,
    parse_error: str | None = None,
) -> tuple:
    """documents + chunks 单事务落库，返回 (doc_id, chunk_records)。

    一次性 add_all + flush，所有 chunk 的自增 id 一次填充，避免逐条
    flush 造成的 N 次往返。同步管线落库即解析完成（status=2）。
    若挂知识库，同一事务内维护 knowledge_bases.doc_count 冗余计数。
    解析发生降级时，把降级原因写入 parse_error，便于排查与展示。
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
            status=(DocumentStatus.DEGRADED if parse_error else DocumentStatus.COMPLETED),
            parse_error=parse_error,
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
                block_type=c.block_type,
                heading_path=json.dumps(c.heading_path or [], ensure_ascii=False),
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
                block_type=c.block_type,
                heading_path=c.heading_path or [],
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
        session.query(DocumentTask).filter(DocumentTask.doc_id == doc_id).delete()
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


# ---------------- 知识库归属与文档级联删除 ----------------

def _validate_kb(kb_id: int) -> None:
    """校验知识库存在，不存在抛业务异常（code=NOT_FOUND）。"""
    session = get_session()
    try:
        exists = session.query(KnowledgeBase.id).filter(KnowledgeBase.id == kb_id).first()
        if exists is None:
            raise BizException(f"知识库不存在: kb_id={kb_id}", code=RespCode.NOT_FOUND)
    finally:
        session.close()


def _check_duplicate(kb_id: int, original_filename: str, overwrite: bool = False) -> None:
    """检查同名文件；显式覆盖时保留旧文档直到新文档成功。

    理由：同名文件通常是同一份内容，重复上传会导致向量库中出现两套相同向量，
    检索时结果成对重复、浪费 top_k 名额（用户侧表现为「来源1和来源2一模一样」）。
    """
    session = get_session()
    try:
        exists = (
            session.query(Document.id)
            .filter(
                Document.kb_id == kb_id,
                Document.original_filename == original_filename,
            )
            .first()
        )
        if exists is not None and not overwrite:
            raise BizException(
                f"该知识库下已存在同名文件: {original_filename}",
                code=RespCode.BIZ_ERROR,
            )
        if exists is not None and overwrite:
            active = (
                session.query(Document.id)
                .filter(
                    Document.kb_id == kb_id,
                    Document.original_filename == original_filename,
                    Document.status.in_([DocumentStatus.PENDING, DocumentStatus.PROCESSING]),
                )
                .first()
            )
            if active is not None:
                raise BizException("该文件已有任务处理中，完成后再执行覆盖", code=RespCode.BIZ_ERROR)
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
        session.query(DocumentTask).filter(DocumentTask.doc_id == doc_id).delete()
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
    asset_dir = settings.document_asset_dir_path / doc.file_id
    if asset_dir.exists():
        import shutil
        shutil.rmtree(asset_dir)
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


def list_document_chunks(file_id: str) -> dict:
    """按 file_id 查询文档全部分块（Chunk 查看器：检查切片质量、排查召回问题）。

    按 chunk_index 升序返回；文档不存在抛 404 业务异常。
    注意：session.close 前必须把 ORM 字段读出来（close 后访问会
    DetachedInstanceError），heading_path 以 JSON 字符串存储，解析失败按空列表兜底。

    Returns:
        {file_id, doc_name, status, parser_name, chunk_count, embedded_count, chunks}
    """
    session = get_session()
    try:
        doc = session.query(Document).filter(Document.file_id == file_id).first()
        if doc is None:
            raise BizException(f"文档不存在: file_id={file_id}", code=RespCode.NOT_FOUND)
        rows = (
            session.query(Chunk)
            .filter(Chunk.doc_id == doc.id)
            .order_by(Chunk.chunk_index.asc())
            .all()
        )
        # 脱离会话前把标量字段取到局部变量，避免 close 后懒加载
        doc_status = doc.status
        parser_name = doc.parser_name
        doc_name = doc.original_filename
        items = [
            {
                "chunk_index": c.chunk_index,
                "content": c.content,
                "page_number": c.page_number,
                "block_type": c.block_type,
                "heading_path": _safe_json_list(c.heading_path),
                "token_count": c.token_count,
                "embedding_status": c.embedding_status,
                "vector_id": c.vector_id,
            }
            for c in rows
        ]
    finally:
        session.close()
    return {
        "file_id": file_id,
        "doc_name": doc_name,
        "status": doc_status,
        "parser_name": parser_name,
        "chunk_count": len(items),
        "embedded_count": sum(1 for it in items if it["embedding_status"] == 1),
        "chunks": items,
    }


async def upload_document_async(
    upload_file: UploadFile,
    kb_id: int | None = None,
    overwrite: bool = False,
) -> UploadResponse:
    """保存文件并创建 pending 文档任务，绝不在请求内解析或调用模型。"""
    from app.service.document_task_service import enqueue_document_task

    target_path = await save_upload_file(upload_file)
    file_sha256 = await run_in_threadpool(sha256_file, target_path)
    try:
        if kb_id is not None:
            await run_in_threadpool(_validate_kb, kb_id)
            if upload_file.filename:
                await run_in_threadpool(_check_duplicate, kb_id, upload_file.filename, overwrite)
        doc_id = await run_in_threadpool(
            _create_pending_document,
            target_path.stem,
            upload_file.filename or "",
            target_path.stat().st_size,
            file_sha256,
            kb_id,
        )
        task_id = await run_in_threadpool(
            enqueue_document_task,
            doc_id,
            max_attempts=settings.document_worker_max_attempts,
        )
        return UploadResponse(
            file_id=target_path.stem,
            original_filename=upload_file.filename or "",
            file_size=target_path.stat().st_size,
            status="pending",
            task_id=task_id,
        )
    except Exception:
        target_path.unlink(missing_ok=True)
        raise


def _create_pending_document(
    file_id: str, original_filename: str, file_size: int, file_sha256: str, kb_id: int | None,
) -> int:
    session = get_session()
    try:
        doc = Document(
            file_id=file_id, kb_id=kb_id, original_filename=original_filename,
            file_type=get_extension(original_filename).lstrip(".") or None,
            file_size=file_size, file_sha256=file_sha256, status=DocumentStatus.PENDING,
            char_count=0, chunk_count=0,
        )
        session.add(doc)
        session.flush()
        if kb_id is not None:
            session.query(KnowledgeBase).filter(KnowledgeBase.id == kb_id).update(
                {KnowledgeBase.doc_count: KnowledgeBase.doc_count + 1}, synchronize_session=False,
            )
        session.commit()
        return doc.id
    except Exception:
        session.rollback()
        logger.exception("创建待处理文档失败: file_id=%s", file_id)
        raise
    finally:
        session.close()


def _purge_replaced_documents(new_doc_id: int) -> None:
    """新文档成功后清理同库同名旧文档，实现先写后删的覆盖语义。"""
    session = get_session()
    try:
        current = session.query(Document).filter(Document.id == new_doc_id).first()
        if current is None or current.kb_id is None:
            return
        old_docs = (
            session.query(Document)
            .filter(
                Document.kb_id == current.kb_id,
                Document.original_filename == current.original_filename,
                Document.id != new_doc_id,
            )
            .all()
        )
        for old_doc in old_docs:
            old_id = old_doc.id
            purge_document(old_doc)
            logger.info(
                "覆盖旧文档: old_doc_id=%s new_doc_id=%s filename=%s",
                old_id, new_doc_id, current.original_filename,
            )
    finally:
        session.close()


def process_document_task(task_id: int) -> None:
    """执行一个已领取任务：解析、结构化分块、向量双写并更新文档终态。"""
    from app.service.document_task_service import mark_task_failed, mark_task_succeeded

    session = get_session()
    doc = session.query(Document).join(DocumentTask, DocumentTask.doc_id == Document.id).filter(
        DocumentTask.id == task_id
    ).first()
    if doc is None:
        session.close()
        raise BizException(f"任务关联文档不存在: task_id={task_id}")
    doc_id, kb_id, file_id, filename = doc.id, doc.kb_id, doc.file_id, doc.original_filename
    session.close()
    path = settings.upload_dir_path / f"{file_id}{get_extension(filename)}"
    try:
        _set_document_status(doc_id, DocumentStatus.PROCESSING)
        # 先确保 collection 存在，再清理重试残留：顺序反了的话，
        # 集合不存在时清理这一步会抛 collection not found，把任务直接判死。
        ensure_collection()
        # 重试前清理上一次可能部分写入的向量，保证幂等重建不产生重复召回。
        delete_by_doc(doc_id)
        parser = get_parser(get_extension(filename))
        parse_result = _load_or_parse_cached(path, parser)
        _persist_assets(file_id, parse_result.assets)
        cleaned = clean_text(parse_result.text)
        cleaned_pages = [clean_text(page) for page in parse_result.page_texts]
        cleaned_blocks = [_clean_block(block) for block in parse_result.blocks]
        chunks = chunk_document(parse_result, cleaned_pages, cleaned_blocks)
        note = _build_degrade_note(parse_result, filename)
        records = _persist_existing_document(doc_id, cleaned, chunks, parse_result.parser_name, note)
        vectors = _embed_chunks([record.content for record in records])
        # 解析+向量化耗时可达分钟级，期间集合仍可能被外部删除，写入前再确认一次。
        ensure_collection()
        insert_chunk_vectors([
            {"id": record.chunk_id, "vector": vector, "doc_id": doc_id,
             "chunk_index": record.chunk_index, "page_number": record.page_number}
            for record, vector in zip(records, vectors)
        ])
        _mark_vectorized(doc_id)
        _purge_replaced_documents(doc_id)
        mark_task_succeeded(task_id)
    except Exception as exc:
        logger.exception("异步文档处理失败: task_id=%s file=%s", task_id, filename)
        try:
            delete_by_doc(doc_id)
        except Exception:
            logger.exception("异步任务失败补偿删除 Milvus 向量失败: doc_id=%s", doc_id)
        mark_task_failed(task_id, str(exc), retry_delay_seconds=settings.document_worker_retry_delay_seconds)


def _set_document_status(doc_id: int, status: DocumentStatus) -> None:
    session = get_session()
    try:
        session.query(Document).filter(Document.id == doc_id).update(
            {Document.status: status, Document.updated_at: datetime.now()}, synchronize_session=False,
        )
        session.commit()
    finally:
        session.close()


def _persist_existing_document(
    doc_id: int, cleaned: str, chunks: list, parser_name: str, parse_error: str | None,
) -> list[_ChunkRecord]:
    session = get_session()
    try:
        doc = session.query(Document).filter(Document.id == doc_id).first()
        if doc is None:
            raise BizException(f"文档不存在: doc_id={doc_id}")
        doc.char_count = len(cleaned)
        doc.chunk_count = len(chunks)
        doc.parser_name = parser_name
        doc.parse_error = parse_error
        doc.status = DocumentStatus.DEGRADED if parse_error else DocumentStatus.COMPLETED
        doc.updated_at = datetime.now()
        session.query(Chunk).filter(Chunk.doc_id == doc_id).delete()
        chunk_objs = [Chunk(
            doc_id=doc_id, kb_id=doc.kb_id, chunk_index=c.chunk_index, content=c.content,
            block_type=c.block_type, heading_path=json.dumps(c.heading_path or [], ensure_ascii=False),
            page_number=c.page_number,
        ) for c in chunks]
        session.add_all(chunk_objs)
        session.flush()
        records = [_ChunkRecord(
            chunk_id=obj.id, content=c.content, chunk_index=c.chunk_index, page_number=c.page_number,
            block_type=c.block_type, heading_path=c.heading_path or [],
        ) for obj, c in zip(chunk_objs, chunks)]
        session.commit()
        return records
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_document_status(file_id: str) -> dict:
    """返回文档及其任务状态，供前端轮询。"""
    session = get_session()
    try:
        doc = session.query(Document).filter(Document.file_id == file_id).first()
        if doc is None:
            raise BizException(f"文档不存在: file_id={file_id}", code=RespCode.NOT_FOUND)
        task = session.query(DocumentTask).filter(DocumentTask.doc_id == doc.id).first()
        return {
            "file_id": doc.file_id, "status": int(doc.status),
            "task_status": int(task.status) if task else None,
            "attempts": task.attempts if task else 0, "chunk_count": doc.chunk_count,
            "parser_name": doc.parser_name, "parse_error": doc.parse_error,
        }
    finally:
        session.close()


def _parser_signature(parser) -> str:
    """缓存签名包含解析器类型和关键配置，避免配置切换误用旧结果。"""
    settings = get_settings()
    return "|".join([
        parser.__class__.__name__, str(settings.pdf_parser), str(settings.mineru_tier),
        str(settings.mineru_api_url),
    ])


def _serialize_parse_result(result) -> str:
    return json.dumps({
        "text": result.text, "page_texts": result.page_texts,
        "blocks": [
            {"block_type": block.block_type, "content": block.content,
             "page_number": block.page_number, "block_index": block.block_index,
             "heading_path": block.heading_path, "metadata": block.metadata}
            for block in result.blocks
        ],
        "assets": result.assets, "parser_name": result.parser_name,
        "parser_version": result.parser_version, "metadata": result.metadata,
    }, ensure_ascii=False)


def _deserialize_parse_result(raw: str):
    from app.service.parser.base import DocumentBlock, ParseResult
    data = json.loads(raw)
    blocks = [DocumentBlock(**block) for block in data.get("blocks", [])]
    return ParseResult(
        text=data.get("text", ""), page_texts=data.get("page_texts", []), blocks=blocks,
        assets=data.get("assets", []), parser_name=data.get("parser_name", "unknown"),
        parser_version=data.get("parser_version"), metadata=data.get("metadata", {}),
    )


def _load_or_parse_cached(path: Path, parser):
    file_hash = sha256_file(path)
    signature = _parser_signature(parser)
    cache_key = hashlib.sha256(f"{file_hash}|{signature}".encode()).hexdigest()
    session = get_session()
    try:
        cached = session.query(ParseCache).filter(ParseCache.cache_key == cache_key).first()
        if cached is not None:
            cached.last_used_at = datetime.now()
            session.commit()
            logger.info("命中解析缓存: file=%s cache_key=%s", path.name, cache_key[:12])
            return _deserialize_parse_result(cached.result_json)
    finally:
        session.close()
    result = parser.parse(path)
    session = get_session()
    try:
        session.add(ParseCache(
            cache_key=cache_key, file_sha256=file_hash, parser_signature=signature,
            result_json=_serialize_parse_result(result), last_used_at=datetime.now(),
        ))
        session.commit()
    except Exception:
        session.rollback()
        logger.exception("写入解析缓存失败: file=%s", path.name)
    finally:
        session.close()
    return result


def _persist_assets(file_id: str, assets: list[dict]) -> None:
    """保存解析器返回的资产清单；二进制下载由解析器后续提供时再补充。"""
    if not assets:
        return
    asset_dir = settings.document_asset_dir_path / file_id
    asset_dir.mkdir(parents=True, exist_ok=True)
    (asset_dir / "manifest.json").write_text(
        json.dumps(assets, ensure_ascii=False, indent=2), encoding="utf-8",
    )
