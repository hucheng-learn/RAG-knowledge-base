"""Pydantic 请求/响应模型。

说明：响应统一走 {code, msg, data} 信封（ApiResponse 泛型模型），
让 OpenAPI 文档能精确描述每个接口的 data 结构——这是纯 dict 响应
做不到的（文档里 data 永远是 any）。
"""

from datetime import datetime
from typing import Generic, List, Optional, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class ApiResponse(BaseModel, Generic[T]):
    """统一响应信封（与 utils/response.py 的返回结构一致）。"""

    code: int = Field(0, description="业务码：0 成功，非 0 失败（见 RespCode）")
    msg: str = Field("success", description="提示信息")
    data: Optional[T] = Field(None, description="业务数据")


class UploadResponse(BaseModel):
    """上传接口响应：文件信息 + 解析结果。

    preview / char_count 由解析模块（任务5/6）填充，本阶段返回 null。
    """

    file_id: str = Field(..., description="文件ID（当前为存储文件名；第二阶段接入 MySQL 后为数据库主键）")
    original_filename: str = Field(..., description="原始文件名（仅展示用，不参与磁盘路径）")
    file_size: int = Field(..., description="文件大小（字节）")
    preview: Optional[str] = Field(None, description="清洗后文本预览片段（解析模块填充）")
    char_count: Optional[int] = Field(None, description="清洗后总字符数（解析模块填充）")
    chunk_count: Optional[int] = Field(None, description="分块数量（第二阶段起填充）")


class KnowledgeBaseCreate(BaseModel):
    """新建知识库请求体。"""

    name: str = Field(..., min_length=1, max_length=64, description="知识库名称（唯一）")
    description: Optional[str] = Field(None, max_length=255, description="描述")


class DocumentBrief(BaseModel):
    """文档简要信息（知识库详情中的文档列表项）。"""

    file_id: str = Field(..., description="文件ID（uuid）")
    original_filename: str = Field(..., description="原始文件名")
    file_size: int = Field(..., description="文件大小（字节）")
    char_count: int = Field(..., description="清洗后总字符数")
    chunk_count: int = Field(..., description="分块数量")
    created_at: datetime = Field(..., description="创建时间")


class KnowledgeBaseSummary(BaseModel):
    """知识库摘要（列表项）。"""

    id: int
    name: str
    description: Optional[str]
    doc_count: int = Field(0, description="包含文档数")
    created_at: datetime


class KnowledgeBaseDetail(BaseModel):
    """知识库详情（含文档列表）。"""

    id: int
    name: str
    description: Optional[str]
    created_at: datetime
    documents: List[DocumentBrief] = Field(default_factory=list, description="文档列表")


class DeleteResponse(BaseModel):
    """删除操作响应（文档/知识库通用）。"""

    deleted: bool = Field(..., description="是否删除成功")
    kb_id: Optional[int] = Field(None, description="被删除的知识库ID")
    file_id: Optional[str] = Field(None, description="被删除的文档file_id")
    name: Optional[str] = Field(None, description="被删除对象名称")
    deleted_documents: int = Field(0, description="级联删除的文档数")
