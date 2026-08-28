"""知识库相关接口：新建/查询/删除。

接口层职责（严格遵守分层）：只接收参数、调 service、包装响应。
知识库的创建/查询/删除业务逻辑都在 knowledge_base_service。
"""

from fastapi import APIRouter
from starlette.concurrency import run_in_threadpool

from app.models.schemas import (
    ApiResponse,
    DeleteResponse,
    KnowledgeBaseCreate,
    KnowledgeBaseDetail,
    KnowledgeBaseSummary,
)
from app.service import knowledge_base_service
from app.utils.response import success

router = APIRouter(prefix="/api/v1/kbs", tags=["知识库"])


@router.post(
    "", response_model=ApiResponse[KnowledgeBaseSummary],
    summary="新建知识库",
    description="name 唯一，≤64 字符；description 可选，≤255 字符。",
)
async def create_kb(body: KnowledgeBaseCreate) -> dict:
    """新建知识库。"""
    result = await run_in_threadpool(
        knowledge_base_service.create_kb, body.name, body.description,
    )
    return success(data=result)


@router.get(
    "", response_model=ApiResponse[list[KnowledgeBaseSummary]],
    summary="查询全部知识库",
)
async def list_kbs() -> dict:
    """查询全部知识库（含每个库的文档数）。"""
    result = await run_in_threadpool(knowledge_base_service.list_kbs)
    return success(data=result)


@router.get(
    "/{kb_id}", response_model=ApiResponse[KnowledgeBaseDetail],
    summary="查询知识库详情",
)
async def get_kb(kb_id: int) -> dict:
    """查询单个知识库详情（含文档列表）。"""
    result = await run_in_threadpool(knowledge_base_service.get_kb, kb_id)
    return success(data=result)


@router.delete(
    "/{kb_id}", response_model=ApiResponse[DeleteResponse],
    summary="删除知识库（级联清理）",
    description="删除知识库会级联删除其下所有文档的 Milvus 向量、MySQL 记录与磁盘文件。",
)
async def delete_kb(kb_id: int) -> dict:
    """删除知识库，级联清理全部文档数据。"""
    result = await run_in_threadpool(knowledge_base_service.delete_kb, kb_id)
    return success(data=result)
