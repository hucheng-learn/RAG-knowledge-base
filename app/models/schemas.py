"""Pydantic 请求/响应模型。

说明：响应统一走 {code, msg, data} 信封（ApiResponse 泛型模型），
让 OpenAPI 文档能精确描述每个接口的 data 结构——这是纯 dict 响应
做不到的（文档里 data 永远是 any）。
"""

from typing import Generic, Optional, TypeVar

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
