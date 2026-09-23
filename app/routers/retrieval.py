"""检索测试接口：只检索不生成。

与 /chat 的区别：不调 LLM，直接返回召回的 chunk + 相似度 + 各阶段耗时，
用于验证检索链路质量（换 embedding / 调 top_k / 调阈值时先在这里看效果）。
"""

from fastapi import APIRouter

from app.models.schemas import ApiResponse, RetrievalTestRequest, RetrievalTestResponse
from app.service import rag_service
from app.utils.response import success

router = APIRouter(prefix="/api/v1/retrieval", tags=["检索测试"])


@router.post(
    "/test",
    response_model=ApiResponse[RetrievalTestResponse],
    summary="检索测试（只检索不生成）",
    description="问题向量化 → Milvus 召回 → 相似度阈值过滤 → MySQL 溯源，不经过 LLM，"
    "返回命中片段与 embedding/retrieval 耗时。",
)
async def retrieval_test(body: RetrievalTestRequest) -> dict:
    """检索测试：只检索不生成，用于调参与效果验证。"""
    result = await rag_service.retrieve_only(body.query, body.kb_id, body.top_k)
    return success(data=result)
