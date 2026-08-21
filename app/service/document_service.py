"""文档业务逻辑层：上传、解析、清洗、分块、元数据入库的编排入口。

职责边界：
- routers 只做参数接收和响应包装；
- 本模块把「保存文件 → 解析 → 清洗 → 分块 → 落库 → 组装响应」串起来；
- 解析/清洗/分块是 CPU 密集任务、MySQL 写入是阻塞 IO，
  全部用 run_in_threadpool 丢到线程池，避免阻塞 asyncio 事件循环。
"""

from pathlib import Path

from fastapi import UploadFile
from starlette.concurrency import run_in_threadpool

from app.config.settings import get_settings
from app.models.orm import get_session
from app.models.orm.chunk import Chunk
from app.models.orm.document import Document
from app.models.schemas import UploadResponse
from app.service.chunk_service import chunk_document
from app.service.parser import get_parser
from app.utils.clean_text import clean_text
from app.utils.file_utils import get_extension, save_upload_file
from app.utils.logger import get_logger

logger = get_logger(__name__)
settings = get_settings()


async def upload_document(upload_file: UploadFile) -> UploadResponse:
    """上传文档：校验 → 保存 → 解析 → 清洗 → 分块 → 入库 → 返回结果。

    全链路任一环节失败（含入库失败）都会清理已落盘文件，
    保证 uploads 目录不存在「没有对应数据库记录」的孤儿文件。
    """
    target_path: Path = await save_upload_file(upload_file)
    file_size = target_path.stat().st_size

    try:
        # 解析（按后缀取解析器，txt/pdf）
        extension = get_extension(upload_file.filename or "")
        parser = get_parser(extension)
        parse_result = await run_in_threadpool(parser.parse, target_path)

        # 清洗（.env 开关可配置）
        cleaned = await run_in_threadpool(clean_text, parse_result.text)

        # 分块（chunk_size + overlap，按页携带页码）
        chunks = await run_in_threadpool(chunk_document, parse_result)

        # 元数据 + 分块落库（单事务）
        document_id = await run_in_threadpool(
            _persist_document, target_path.stem, upload_file.filename,
            file_size, cleaned, chunks,
        )
    except Exception:
        # 解析/清洗/分块/入库任一失败：清理已落盘文件，避免无效文件堆积
        target_path.unlink(missing_ok=True)
        logger.warning("文档处理失败已清理文件: %s", target_path.name)
        raise

    # 预览片段：截断到配置长度，超长加省略号
    preview = cleaned[: settings.preview_max_chars]
    if len(cleaned) > settings.preview_max_chars:
        preview += "..."

    logger.info(
        "文档入库完成: 数据库id=%s file_id=%s 文件名=%s 页数=%d "
        "清洗后字符数=%d 分块数=%d 大小=%d字节",
        document_id, target_path.stem, upload_file.filename,
        len(parse_result.page_texts), len(cleaned), len(chunks), file_size,
    )
    return UploadResponse(
        file_id=target_path.stem,
        original_filename=upload_file.filename or "",
        file_size=file_size,
        preview=preview,
        char_count=len(cleaned),
        chunk_count=len(chunks),
    )


def _persist_document(
    file_id: str,
    original_filename: str,
    file_size: int,
    cleaned: str,
    chunks: list,
) -> int:
    """文档元数据 + 全部分块写入 MySQL（单个事务）。

    事务保证：documents 行与 chunks 行要么全部成功、要么全部回滚，
    不会出现「有文档没分块」的中间状态。

    Args:
        file_id: 上传接口返回的 uuid 文件ID（documents.file_id 唯一键）。
        chunks: chunk_service.TextChunk 列表。

    Returns:
        新插入的 documents.id。
    """
    session = get_session()
    try:
        doc = Document(
            file_id=file_id,
            original_filename=original_filename or "",
            file_size=file_size,
            char_count=len(cleaned),
            chunk_count=len(chunks),
        )
        session.add(doc)
        session.flush()  # flush 后 doc.id 已由数据库自增生成

        for c in chunks:
            session.add(
                Chunk(
                    doc_id=doc.id,
                    chunk_index=c.chunk_index,
                    content=c.content,
                    page_number=c.page_number,
                    # vector_id 暂为 NULL，第三阶段写入 Milvus 向量 id
                )
            )
        session.commit()
        return doc.id
    except Exception:
        session.rollback()
        logger.exception("文档元数据入库失败: file_id=%s", file_id)
        raise
    finally:
        session.close()
