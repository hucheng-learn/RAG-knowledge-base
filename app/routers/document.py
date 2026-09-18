"""文档相关接口：文件上传、删除。

接口层职责（严格遵守分层）：
- 只负责接收参数、调用 service、包装响应；
- 不写任何业务逻辑（校验/保存/解析/删除都在 service 层）。
"""

from typing import Optional

from fastapi import APIRouter, File, Query, UploadFile
from starlette.concurrency import run_in_threadpool

from app.models.schemas import ApiResponse, DeleteResponse, DocumentStatusResponse, UploadResponse
from app.service import document_service
from app.utils.response import success

router = APIRouter(prefix="/api/v1/documents", tags=["文档"])


@router.post(
    "/upload",
    response_model=ApiResponse[UploadResponse],
    summary="上传文档（异步处理）",
    description="支持txt / md / pdf / docx / xls / 图片等，单文件 ≤20MB；可选指定所属知识库 kb_id。",
)
async def upload_document(
    file: UploadFile = File(..., description="待上传文件"),
    kb_id: Optional[int] = Query(None, description="可选，指定所属知识库ID"),
    overwrite: bool = Query(False, description="同名文档是否在新文档处理成功后替换旧文档"),
) -> dict:
    """上传文档：保存后立即入队，解析和向量化由后台 worker 执行。"""
    result = await document_service.upload_document_async(file, kb_id, overwrite)
    return success(data=result)


@router.get(
    "/{file_id}/status",
    response_model=ApiResponse[DocumentStatusResponse],
    summary="查询文档处理状态",
)
async def document_status(file_id: str) -> dict:
    result = await run_in_threadpool(document_service.get_document_status, file_id)
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
