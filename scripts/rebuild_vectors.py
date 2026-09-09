# -*- coding: utf-8 -*-
"""向量重建工具：把 MySQL 中已入库但 Milvus 缺失的向量补齐。

适用场景（对应 TECH_DESIGN 6.5「对账 + 补偿」）：
    Milvus 数据卷重置/丢失 → MySQL 有 chunk 记录但 Milvus 没有对应向量。

原理（纯增量、无任何删除）：
    读 MySQL 全部 chunks → 批量 embedding → 写回 Milvus（主键=chunk.id）→ 回填 vector_id。

幂等安全：
    - 只 INSERT/UPDATE，不 DELETE；
    - 已有向量的 chunk 会重写同 id 的向量（覆盖，无副作用）；
    - 源文件、documents 记录均不受影响。

用法：
    conda activate rag_kb
    python scripts/rebuild_vectors.py            # 全量重建
    python scripts/rebuild_vectors.py --doc-id 2 # 只重建某篇文档
"""

import argparse
import time
from pathlib import Path

from app.config.settings import get_settings
from app.models.orm import get_session
from app.models.orm.chunk import Chunk
from app.service.embedding_service import get_embedding_service
from app.service.vector_service import (
    ensure_collection,
    insert_chunk_vectors,
)

settings = get_settings()


def load_chunks(doc_id: int | None = None) -> list:
    """从 MySQL 读 chunk 记录（可指定文档）。"""
    session = get_session()
    try:
        q = session.query(Chunk)
        if doc_id is not None:
            q = q.filter(Chunk.doc_id == doc_id)
        return q.order_by(Chunk.doc_id, Chunk.chunk_index).all()
    finally:
        session.close()


def mark_vectorized(doc_ids: set) -> None:
    """回填 vector_id = chunk.id（标记已向量化，与入库流程一致）。"""
    session = get_session()
    try:
        if doc_ids:
            session.query(Chunk).filter(Chunk.doc_id.in_(doc_ids)).update(
                {Chunk.vector_id: Chunk.id, Chunk.embedding_status: 1},
                synchronize_session=False,
            )
            session.commit()
    finally:
        session.close()


def rebuild(doc_id: int | None = None) -> None:
    """全量（或指定文档）重建向量。"""
    chunks = load_chunks(doc_id)
    if not chunks:
        print(f"没有需要重建的 chunk（doc_id={doc_id or '全部'}）")
        return

    print(f"读取 {len(chunks)} 个 chunk，开始向量化…")
    svc = get_embedding_service()
    texts = [c.content for c in chunks]
    t0 = time.time()
    vectors = svc.embed_texts(texts)
    print(f"向量化完成: {len(vectors)} 条 x {svc.dim} 维，耗时 {time.time()-t0:.1f}s")

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
    mark_vectorized({c.doc_id for c in chunks})

    docs = sorted({c.doc_id for c in chunks})
    print(f"✅ 重建完成: {len(records)} 条向量已写入 Milvus，涉及文档 {docs}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="向量重建工具（对账补偿）")
    parser.add_argument("--doc-id", type=int, default=None, help="只重建指定文档")
    args = parser.parse_args()
    rebuild(args.doc_id)
