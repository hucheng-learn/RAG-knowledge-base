"""RAG 问答编排：问题向量化 → Milvus 召回 → 溯源 → 拼上下文 → 流式生成。

全链路（对应 PROJECT_PLAN 3.2 问答流程）：
用户提问 → question 向量化 → Milvus 召回 topN → 回查 MySQL 拿原文/页码/文档名
→ 组装系统提示词 + 检索上下文 + 问题 → SSE 流式回答 + 溯源。

以异步生成器的形式产出 SSE 事件（start/delta/done），
由 routers/chat.py 编码成 text/event-stream。
"""

from typing import AsyncIterator, Optional

from starlette.concurrency import run_in_threadpool

from app.config.settings import get_settings
from app.models.orm import get_session
from app.models.orm.chunk import Chunk
from app.models.orm.document import Document
from app.service.embedding_service import get_embedding_service
from app.service.llm_service import stream_chat
from app.service.vector_service import search as milvus_search
from app.utils.logger import get_logger

logger = get_logger(__name__)
settings = get_settings()

# 系统提示词：约束模型只依据检索上下文作答，禁止编造
_SYSTEM_PROMPT = (
    "你是一个企业知识库问答助手。请严格基于提供的「参考资料」回答用户问题。\n"
    "规则：\n"
    "1. 只使用参考资料中的信息作答，不要编造参考资料之外的内容；\n"
    "2. 回答中可用 [来源N] 标注依据了哪条资料；\n"
    "3. 若参考资料不足以回答问题，明确回答\"资料中未找到相关信息\"；\n"
    "4. 回答简洁、准确、条理清晰。"
)


async def rag_answer(
    query: str,
    kb_id: Optional[int] = None,
    top_k: int = 4,
) -> AsyncIterator[dict]:
    """RAG 问答异步生成器。

    Args:
        query: 用户问题。
        kb_id: 可选，限定在指定知识库内检索。
        top_k: 召回条数。

    Yields:
        {"event": "start", "data": [溯源片段...]}
        {"event": "delta", "data": "回答增量文本"}
        {"event": "done", "data": {"code","msg","answer","token_count"}}
    """
    # 1. 问题向量化（GPU）
    svc = get_embedding_service()
    qv = await run_in_threadpool(svc.embed_query, query)

    # 2. 召回：可选按知识库过滤（先取该库 doc_ids）
    doc_ids = None
    if kb_id is not None:
        doc_ids = await run_in_threadpool(_get_kb_doc_ids, kb_id)
    hits = await run_in_threadpool(milvus_search, qv, top_k, doc_ids)

    # 2b. 相似度阈值过滤：Milvus 总是返回 top_k 条，即使相似度很低；
    #     低于阈值的弱匹配视为"无相关"，避免模型答非所问（减少幻觉）
    hits = [h for h in hits if h["distance"] >= settings.rag_min_similarity]

    # 3. 溯源：回查 MySQL 拿原文 / 页码 / 文档名
    trace = await run_in_threadpool(_build_trace, hits)

    # 4a. 无召回：直接结束，不调大模型
    if not trace:
        yield {"event": "start", "data": []}
        yield {
            "event": "done",
            "data": {
                "code": 0,
                "msg": "未检索到相关资料，请换个问法或先上传相关文档",
                "answer": "",
                "token_count": 0,
            },
        }
        return

    # 4b. 组装上下文 + 系统提示词
    context = "\n\n".join(f"[来源{t['idx']}] {t['content']}" for t in trace)
    user_msg = f"参考资料：\n{context}\n\n问题：{query}"

    # 5. 先发溯源，再流式回答
    yield {"event": "start", "data": trace}
    answer_parts = []
    async for token in stream_chat(_SYSTEM_PROMPT, user_msg):
        answer_parts.append(token)
        yield {"event": "delta", "data": token}

    answer = "".join(answer_parts)
    yield {
        "event": "done",
        "data": {
            "code": 0,
            "msg": "ok",
            "answer": answer,
            "token_count": len(answer),
        },
    }


def _get_kb_doc_ids(kb_id: int) -> list:
    """取某知识库下的所有文档 id，用于检索过滤。"""
    session = get_session()
    try:
        rows = session.query(Document.id).filter(Document.kb_id == kb_id).all()
        return [r[0] for r in rows]
    finally:
        session.close()


def _build_trace(hits: list) -> list:
    """根据 Milvus 命中记录，回查 MySQL 组装溯源片段。

    返回按相似度排序的 [{idx, doc_name, content, page, similarity}, ...]
    """
    if not hits:
        return []
    chunk_ids = [h["chunk_id"] for h in hits]
    session = get_session()
    try:
        rows = (
            session.query(Chunk, Document)
            .join(Document, Chunk.doc_id == Document.id)
            .filter(Chunk.id.in_(chunk_ids))
            .all()
        )
        by_id = {c.id: (c, d) for c, d in rows}
    finally:
        session.close()

    trace = []
    for i, hit in enumerate(hits, start=1):
        pair = by_id.get(hit["chunk_id"])
        if pair is None:
            continue  # Milvus 有向量但 MySQL 无记录（对账兜底）
        chunk, doc = pair
        trace.append({
            "idx": i,
            "doc_name": doc.original_filename,
            "content": chunk.content,
            "page": chunk.page_number,
            "similarity": round(hit["distance"], 4),
        })
    return trace
