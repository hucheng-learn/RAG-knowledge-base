"""文件工具：上传文件的校验、存储命名、保存。

职责边界：只做「文件落盘」这件事，返回保存后的路径；
解析/清洗等业务逻辑在 service 层，不放在这里。
"""

import uuid
from pathlib import Path

from fastapi import UploadFile

from app.config.settings import get_settings
from app.utils.exceptions import BizException
from app.utils.logger import get_logger

logger = get_logger(__name__)

# 分块读取大小：边读边写，避免整个文件一次性载入内存
_CHUNK_SIZE = 1024 * 1024  # 1MB


def get_extension(filename: str) -> str:
    """提取小写后缀名（含点，如 ".txt"）；无后缀返回空字符串。"""
    return Path(filename).suffix.lower()


def validate_extension(filename: str) -> None:
    """后缀名校验：缺失或不在白名单（.env ALLOWED_EXTENSIONS）→ 业务异常。

    Args:
        filename: 上传文件的原始文件名（可能为 None，先判空）。
    """
    if not filename:
        raise BizException("请求缺少文件名")
    ext = get_extension(filename)
    if not ext:
        raise BizException(f"文件缺少后缀名: {filename}")
    allowed = get_settings().allowed_extension_set
    if ext not in allowed:
        raise BizException(f"不支持的文件类型: {ext}，仅支持 {sorted(allowed)}")


def generate_storage_name(original_filename: str) -> str:
    """生成存储文件名：uuid4.hex + 原始后缀。

    为什么不用原始文件名：
    1. 同名文件会互相覆盖 → uuid 天然去重；
    2. 中文/特殊字符文件名在部分文件系统有兼容问题；
    3. 恶意构造的 "../xxx" 路径穿越在 uuid 命名下天然免疫
       （原始文件名只作展示，永不参与磁盘路径拼接）。
    """
    ext = get_extension(original_filename)
    return f"{uuid.uuid4().hex}{ext}"


async def save_upload_file(upload_file: UploadFile) -> Path:
    """校验并保存上传文件到 uploads 目录，返回保存后的绝对路径。

    流程：后缀校验 → 分块读取（边读边累计字节数，超限立即中止）→ 落盘。

    为什么用「边读边校验大小」而不是先看 Content-Length：
    1. 部分客户端/代理不携带 Content-Length；
    2. 流式读取中的累计字节数才是权威值；
    3. 超限时提前中断，避免把 20MB+ 的数据全读进来再丢弃。
    任何失败都会清理半成品文件，保证 uploads 目录不留脏数据。
    """
    settings = get_settings()
    validate_extension(upload_file.filename)

    storage_name = generate_storage_name(upload_file.filename)
    target_path = settings.upload_dir_path / storage_name

    saved = 0
    try:
        # 分块读取并落盘，同时累计实际字节数
        with target_path.open("wb") as f:
            while True:
                chunk = await upload_file.read(_CHUNK_SIZE)
                if not chunk:
                    break
                saved += len(chunk)
                if saved > settings.max_upload_size_bytes:
                    raise BizException(
                        f"文件大小 {saved / 1024 / 1024:.2f}MB 超过上限 {settings.max_upload_size_mb}MB"
                    )
                f.write(chunk)
    except BizException:
        # 业务异常：清理半成品后原样抛出（保留业务码）
        target_path.unlink(missing_ok=True)
        raise
    except Exception:
        # 系统异常：清理半成品后按系统异常处理（打完整堆栈）
        target_path.unlink(missing_ok=True)
        logger.exception("文件保存失败: %s", storage_name)
        raise

    # 空文件无业务意义，拒绝并清理
    if saved == 0:
        target_path.unlink(missing_ok=True)
        raise BizException("文件内容为空")

    logger.info(
        "文件已保存: 原始文件名=%s 存储名=%s 大小=%d字节",
        upload_file.filename, storage_name, saved,
    )
    return target_path
