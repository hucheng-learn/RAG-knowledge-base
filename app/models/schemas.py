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
    """上传接口响应：文件信息 + 解析结果。"""

    file_id: str = Field(..., description="文件ID（当前为存储文件名；第二阶段接入 MySQL 后为数据库主键）")
    original_filename: str = Field(..., description="原始文件名（仅展示用，不参与磁盘路径）")
    file_size: int = Field(..., description="文件大小（字节）")
    preview: Optional[str] = Field(None, description="清洗后文本预览片段（解析模块填充）")
    char_count: Optional[int] = Field(None, description="清洗后总字符数（解析模块填充）")
    chunk_count: Optional[int] = Field(None, description="分块数量（第二阶段起填充）")
    parser_name: Optional[str] = Field(None, description="实际使用的解析器（txt/pdfplumber/mineru）")
    degraded: Optional[bool] = Field(None, description="是否发生了降级解析（如 MinerU 失败回退 pdfplumber）")
    status: Optional[str] = Field(None, description="文档处理状态")
    task_id: Optional[int] = Field(None, description="异步处理任务ID")


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
    status: int = Field(0, description="处理状态: 0待解析/1处理中/2完成/3失败/4降级完成")
    parser_name: Optional[str] = Field(None, description="实际解析器")
    parse_error: Optional[str] = Field(None, description="处理错误或降级说明")


class DocumentStatusResponse(BaseModel):
    """异步文档处理状态。"""

    file_id: str
    status: int
    task_status: Optional[int] = None
    attempts: int = 0
    chunk_count: int = 0
    parser_name: Optional[str] = None
    parse_error: Optional[str] = None


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


class ChatRequest(BaseModel):
    """RAG 问答请求体（SSE 流式响应，不用统一信封）。"""

    query: str = Field(..., min_length=1, max_length=2000, description="用户问题")
    kb_id: Optional[int] = Field(None, description="可选，限定在指定知识库内检索")
    top_k: int = Field(4, ge=1, le=10, description="召回条数（1-10）")


class RetrievalTestRequest(BaseModel):
    """检索测试请求体（只检索不生成，用于调参与效果验证）。"""

    query: str = Field(..., min_length=1, max_length=2000, description="测试问题")
    kb_id: Optional[int] = Field(None, description="可选，限定在指定知识库内检索")
    top_k: int = Field(4, ge=1, le=10, description="召回条数（1-10）")


class RetrievalHit(BaseModel):
    """检索命中片段（MySQL 溯源，含相似度）。"""

    idx: int = Field(..., description="来源编号（1 起，对应问答提示词里的 [来源N]）")
    doc_name: str = Field(..., description="文档名")
    file_id: str = Field(..., description="文档唯一标识（前端跳转 Chunk 查看器用）")
    chunk_index: int = Field(0, description="命中的 chunk 在文档内的序号（0 起）")
    content: str = Field(..., description="命中的 chunk 原文")
    page: Optional[int] = Field(None, description="来源页码")
    similarity: float = Field(..., description="余弦相似度（已过 rag_min_similarity 阈值）")


class RetrievalTestResponse(BaseModel):
    """检索测试结果（含各阶段耗时，便于定位瓶颈）。"""

    query: str
    kb_id: Optional[int] = None
    top_k: int
    hits: List[RetrievalHit] = Field(default_factory=list)
    embedding_ms: float = Field(0, description="问题向量化耗时（ms）")
    retrieval_ms: float = Field(0, description="向量化+召回+溯源总耗时（ms）")
    total_ms: float = Field(0, description="接口端到端耗时（ms）")


class ChunkItem(BaseModel):
    """单个分块（原文 ↔ 元数据可追溯，含向量入库状态）。"""

    chunk_index: int = Field(..., description="文档内块编号（0 起）")
    content: str = Field(..., description="块原始文本")
    page_number: int = Field(1, description="来源页码（1 起）")
    block_type: Optional[str] = Field(None, description="结构化块类型(text/table/title/list等)")
    heading_path: List[str] = Field(default_factory=list, description="标题层级路径")
    token_count: Optional[int] = Field(None, description="token 数量")
    embedding_status: int = Field(0, description="嵌入状态: 0待嵌入 1已嵌入 2失败")
    vector_id: Optional[str] = Field(None, description="Milvus 向量ID")


class DocumentChunksResponse(BaseModel):
    """文档分块列表（Chunk 查看器：切片质量检查与召回问题排查）。"""

    file_id: str
    doc_name: str
    status: int = Field(..., description="文档状态（同文档列表的 0-4）")
    parser_name: Optional[str] = None
    chunk_count: int = Field(0, description="分块总数")
    embedded_count: int = Field(0, description="已写入 Milvus 的分块数")
    chunks: List[ChunkItem] = Field(default_factory=list)
