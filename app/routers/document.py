"""文档相关接口：文件上传、删除。

接口层职责（严格遵守分层）：
- 只负责接收参数、调用 service、包装响应；
- 不写任何业务逻辑（校验/保存/解析/删除都在 service 层）。
"""

from typing import Optional

from fastapi import APIRouter, File, Query, UploadFile
from starlette.concurrency import run_in_threadpool

from app.models.schemas import ApiResponse, DeleteResponse, UploadResponse
from app.service import document_service
from app.utils.response import success

router = APIRouter(prefix="/api/v1/documents", tags=["文档"])


@router.post(
    "/upload",
    response_model=ApiResponse[UploadResponse],
    summary="上传文档（同步解析）",
    description="支持 txt / 可复制文本 PDF，单文件 ≤ 20MB；可选指定所属知识库 kb_id。",
)
async def upload_document(
    file: UploadFile = File(..., description="待上传文件"),
    kb_id: Optional[int] = Query(None, description="可选，指定所属知识库ID"),
) -> dict:
    """上传文档：校验 → 保存 → 解析 → 分块 → 向量入库 → 返回结果。"""
    result = await document_service.upload_document(file, kb_id)
    return success(data=result)


@router.delete(
    "/{file_id}",
    response_model=ApiResponse[DeleteResponse],
    summary="删除文档（级联清理）",
    description="删除文档的 Milvus 向量、MySQL 记录与磁盘文件。",
)
async def delete_document(file_id: str) -> dict:
    """删除单个文档，级联清理 Milvus + MySQL + 磁盘文件。"""
    result = await run_in_threadpool(document_service.delete_document, file_id)
    return success(data=result)
