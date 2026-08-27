"""Milvus 向量库操作封装。

设计（面试点）：
1. **Milvus 只存向量 + 少量过滤字段，chunk 原文在 MySQL** —— 元数据
   单一来源（MySQL），避免双写不一致；搜索命中后凭 chunk_id 回查 MySQL；
2. **主键 id = MySQL chunks.id（INT64）** —— 实现 MySQL↔Milvus 一一对应，
   也便于双写一致性对账（两边 id 集合比对）；
3. 过滤字段 doc_id / chunk_index / page_number：按文档删除、按文档过滤检索
   （不用分区，简化；量级大再考虑 partition）；
4. 相似度 COSINE（语义检索标准）+ HNSW 图索引（高召回，可配 M/efConstruction）；
5. collection 惰性创建（ensure_collection 幂等），客户端进程内单例。
"""

from pymilvus import DataType, MilvusClient

from app.config.settings import get_settings
from app.utils.logger import get_logger

logger = get_logger(__name__)

_client = None
_collection_ready = False


def get_client() -> MilvusClient:
    """获取 Milvus 客户端（进程内单例，惰性创建）。"""
    global _client
    if _client is None:
        settings = get_settings()
        _client = MilvusClient(uri=f"http://{settings.milvus_host}:{settings.milvus_port}")
    return _client


def ensure_collection() -> None:
    """确保 collection 存在（幂等）：不存在则按 schema 创建。"""
    global _collection_ready
    if _collection_ready:
        return
    settings = get_settings()
    client = get_client()
    if not client.has_collection(settings.milvus_collection):
        schema = MilvusClient.create_schema(auto_id=False, enable_dynamic_field=False)
        schema.add_field("id", DataType.INT64, is_primary=True)          # = MySQL chunks.id
        schema.add_field("vector", DataType.FLOAT_VECTOR, dim=settings.embedding_dim)
        schema.add_field("doc_id", DataType.INT64)
        schema.add_field("chunk_index", DataType.INT64)
        schema.add_field("page_number", DataType.INT64)
        client.create_collection(
            collection_name=settings.milvus_collection,
            schema=schema,
            metric_type=settings.milvus_metric,
            index_params={
                "index_type": settings.milvus_index_type,
                "metric_type": settings.milvus_metric,
                "params": {"M": 16, "efConstruction": 200},
            },
        )
        logger.info(
            "Milvus collection 已创建: %s dim=%d metric=%s index=%s",
            settings.milvus_collection, settings.embedding_dim,
            settings.milvus_metric, settings.milvus_index_type,
        )
    _collection_ready = True


def insert_chunk_vectors(records: list) -> None:
    """批量插入块向量。

    Args:
        records: 每个元素 {id, vector, doc_id, chunk_index, page_number}。
    """
    if not records:
        return
    settings = get_settings()
    client = get_client()
    client.insert(settings.milvus_collection, data=records)
    logger.info("Milvus 插入 %d 条向量: doc_id=%s", len(records), records[0].get("doc_id"))


def search(query_vector: list, top_k: int, doc_ids: list = None) -> list:
    """相似度检索，返回命中的 chunk 信息。

    Args:
        query_vector: 查询向量。
        top_k: 返回条数。
        doc_ids: 可选，限定在指定文档内检索。

    Returns:
        [{chunk_id, doc_id, chunk_index, page_number, distance}, ...]
    """
    settings = get_settings()
    client = get_client()
    expr = None
    if doc_ids:
        # 用 in 表达式做文档级过滤
        expr = f"doc_id in {doc_ids}"
    hits = client.search(
        collection_name=settings.milvus_collection,
        data=[query_vector],
        limit=top_k,
        filter=expr,
        output_fields=["doc_id", "chunk_index", "page_number"],
    )
    results = []
    for hit in hits[0]:
        entity = hit["entity"]
        results.append({
            "chunk_id": hit["id"],
            "doc_id": entity["doc_id"],
            "chunk_index": entity["chunk_index"],
            "page_number": entity["page_number"],
            "distance": hit["distance"],
        })
    return results


def delete_by_doc(doc_id: int) -> None:
    """按文档删除全部向量（第四阶段删除文档时用）。"""
    settings = get_settings()
    get_client().delete(settings.milvus_collection, filter=f"doc_id == {doc_id}")
    logger.info("Milvus 删除文档向量: doc_id=%s", doc_id)
