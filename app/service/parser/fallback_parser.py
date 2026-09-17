"""解析器降级封装：主解析器失败时自动回退到备用解析器。

典型用途：`PDF_PARSER=mineru` 时，MinerU 服务不可用或解析失败 → 回退 `pdfplumber`，
避免单个解析器故障导致整个上传失败。

**降级结果不伪装成正常结果**：在 `ParseResult.metadata` 标记
`degraded=True` / `degrade_reason` / `primary_parser`，上层据此记录与展示。
"""

from pathlib import Path

from app.service.parser.base import DocumentParser, ParseResult
from app.utils.logger import get_logger

logger = get_logger(__name__)


class FallbackDocumentParser(DocumentParser):
    """先试主解析器，失败则用备用解析器，并在结果里标记降级。"""

    def __init__(self, primary: DocumentParser, backup: DocumentParser) -> None:
        self._primary = primary
        self._backup = backup

    def parse(self, file_path: Path) -> ParseResult:
        reason = ""
        try:
            return self._primary.parse(file_path)
        except Exception as exc:  # noqa: BLE001 —— 主解析器任何失败都降级
            # 注意：except 块结束后 exc 会被 Python 删除，先取出原因字符串
            reason = str(exc)
            logger.warning(
                "主解析器 %s 失败，降级到 %s: 文件=%s 原因=%s",
                type(self._primary).__name__, type(self._backup).__name__,
                file_path.name, reason,
            )

        result = self._backup.parse(file_path)
        result.metadata = {
            **result.metadata,
            "degraded": True,
            "primary_parser": type(self._primary).__name__,
            "backup_parser": type(self._backup).__name__,
            "degrade_reason": reason,
        }
        logger.info(
            "解析已降级: 文件=%s 解析器=%s 原解析器=%s",
            file_path.name, result.parser_name, type(self._primary).__name__,
        )
        return result
