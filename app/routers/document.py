"""文档相关接口：文件上传。

接口层职责（严格遵守分层）：
- 只负责接收参数、调用 service、包装响应；
- 不写任何业务逻辑（校验/保存/解析都在 service 层）。
"""

from fastapi import APIRouter, File, UploadFile

from app.models.schemas import ApiResponse, UploadResponse
from app.service import document_service
from app.utils.response import success

router = APIRouter(prefix="/api/v1/documents", tags=["文档"])


@router.post(
    "/upload",
    response_model=ApiResponse[UploadResponse],
    summary="上传文档（同步解析）",
    description="支持 txt / 可复制文本 PDF，单文件 ≤ 20MB；返回文件信息与解析结果。",
)
async def upload_document(
    file: UploadFile = File(..., description="待上传文件"),
) -> dict:
    """上传文档接口：校验 → 保存 → （解析，任务6接入）→ 返回结果。"""
    result = await document_service.upload_document(file)
    return success(data=result)
