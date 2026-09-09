"""向量重建/对账核心逻辑（可复用：CLI 脚本、定时调度器、查询兜底触发）。

能力：幂等补齐向量 —— 读 MySQL chunks → embedding → 写 Milvus → 回填 vector_id。
纯增量、无任何删除；对已有向量的 chunk 覆盖写同 id 向量（无副作用）。

设计（面试点）：
1. 与 scripts/rebuild_vectors.py（薄壳 CLI）解耦，核心可被任意调用方复用；
2. 第六阶段接入 APScheduler 后，定时对账直接调 rebuild_documents()；
3. 查询兜底（rag_service）检测到向量缺失时，后台触发同一函数。
"""

from app.models.orm import get_session
from app.models.orm.chunk import Chunk
from app.service.embedding_service import get_embedding_service
from app.service.vector_service import ensure_collection, insert_chunk_vectors
from app.utils.logger import get_logger

logger = get_logger(__name__)


def rebuild_documents(doc_ids: list) -> int:
    """重建指定文档的全部向量，返回重建的 chunk 条数。幂等。

    Args:
        doc_ids: 文档 id 列表（空列表直接返回 0）。

    Returns:
        写入 Milvus 的向量条数。
    """
    if not doc_ids:
        return 0
    chunks = _load_chunks(doc_ids)
    if not chunks:
        logger.info("无需重建: doc_ids=%s 无 chunk", doc_ids)
        return 0

    _embed_and_insert(chunks)
    _mark_vectorized(doc_ids)
    logger.info("向量重建完成: doc_ids=%s chunks=%d", doc_ids, len(chunks))
    return len(chunks)


def rebuild_all() -> dict:
    """全量重建所有文档的向量（定时对账的兜底入口）。

    Returns:
        {"docs": [...], "chunks": N}
    """
    session = get_session()
    try:
        rows = session.query(Chunk.doc_id).distinct().all()
        all_doc_ids = [r[0] for r in rows]
    finally:
        session.close()
    total = rebuild_documents(all_doc_ids) if all_doc_ids else 0
    return {"docs": all_doc_ids, "chunks": total}


def _load_chunks(doc_ids: list) -> list:
    """按文档 id 读全部 chunk（按 doc/chunk_index 排序，保证主键稳定）。"""
    session = get_session()
    try:
        return (
            session.query(Chunk)
            .filter(Chunk.doc_id.in_(doc_ids))
            .order_by(Chunk.doc_id, Chunk.chunk_index)
            .all()
        )
    finally:
        session.close()


def _embed_and_insert(chunks: list) -> None:
    """批量向量化并写 Milvus（vector 主键 = chunk.id）。"""
    svc = get_embedding_service()
    texts = [c.content for c in chunks]
    vectors = svc.embed_texts(texts)

    ensure_collection()
    records = [
        {
            "id": c.id,
            "vector": vec,
            "doc_id": c.doc_id,
            "chunk_index": c.chunk_index,
            "page_number": c.page_number,
        }
        for c, vec in zip(chunks, vectors)
    ]
    insert_chunk_vectors(records)


def _mark_vectorized(doc_ids: list) -> None:
    """回填 vector_id = chunk.id，置 embedding_status=1（与入库流程一致）。"""
    session = get_session()
    try:
        session.query(Chunk).filter(Chunk.doc_id.in_(doc_ids)).update(
            {Chunk.vector_id: Chunk.id, Chunk.embedding_status: 1},
            synchronize_session=False,
        )
        session.commit()
    finally:
        session.close()
