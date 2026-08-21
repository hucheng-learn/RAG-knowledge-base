"""文档业务逻辑层：上传、解析、清洗的编排入口。

职责边界：
- routers 只做参数接收和响应包装；
- 本模块把「保存文件 → 解析 → 清洗 → 组装响应」串起来；
- CPU 密集的解析/清洗用 run_in_threadpool 丢到线程池，
  避免阻塞 asyncio 事件循环（async 接口里不能直接跑同步重活）。
"""

from pathlib import Path

from fastapi import UploadFile
from starlette.concurrency import run_in_threadpool

from app.config.settings import get_settings
from app.models.schemas import UploadResponse
from app.service.parser import get_parser
from app.utils.clean_text import clean_text
from app.utils.file_utils import get_extension, save_upload_file
from app.utils.logger import get_logger

logger = get_logger(__name__)
settings = get_settings()


async def upload_document(upload_file: UploadFile) -> UploadResponse:
    """上传文档：校验 → 保存 → 解析 → 清洗 → 返回文件信息与解析结果。

    流程：
    1. save_upload_file：后缀/大小校验 + uuid 落盘（异步分块读写）；
    2. get_parser：按后缀取解析器（txt/pdf）；
    3. parser.parse：提取全文与逐页文本（CPU 密集 → 线程池）；
    4. clean_text：按 .env 开关清洗（CPU 密集 → 线程池）；
    5. 组装响应：preview 截断 + char_count。
    """
    target_path: Path = await save_upload_file(upload_file)
    file_size = target_path.stat().st_size

    try:
        # 解析 + 清洗（线程池执行，不阻塞事件循环）
        extension = get_extension(upload_file.filename or "")
        parser = get_parser(extension)
        parse_result = await run_in_threadpool(parser.parse, target_path)
        cleaned = await run_in_threadpool(clean_text, parse_result.text)
    except Exception:
        # 解析失败（扫描版/损坏/编码无法识别）：清理已落盘文件，
        # 避免 uploads 目录堆积无法使用的无效文件
        target_path.unlink(missing_ok=True)
        logger.warning("解析失败已清理文件: %s", target_path.name)
        raise

    # 预览片段：截断到配置长度，超长加省略号
    preview = cleaned[: settings.preview_max_chars]
    if len(cleaned) > settings.preview_max_chars:
        preview += "..."

    logger.info(
        "解析完成: 文件名=%s 页数=%d 清洗后字符数=%d 文件大小=%d字节",
        upload_file.filename, len(parse_result.page_texts), len(cleaned), file_size,
    )
    return UploadResponse(
        file_id=target_path.stem,
        original_filename=upload_file.filename or "",
        file_size=file_size,
        preview=preview,
        char_count=len(cleaned),
    )
