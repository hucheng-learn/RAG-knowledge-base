"""txt 解析器：直接读取文本文件。

核心问题：编码识别。Windows 上 txt 常见 UTF-8 与 GBK 两种编码，
用「尝试解码」策略：先 UTF-8（无 BOM 也能识别），失败回退 GBK，
都失败才报业务异常——比依赖 BOM 判断更鲁棒。
"""

from pathlib import Path

from app.service.parser.base import DocumentParser, ParseResult
from app.utils.exceptions import BizException

# 按优先级尝试的编码列表
_ENCODINGS = ("utf-8", "gbk")


class TxtParser(DocumentParser):
    """txt 解析：UTF-8/GBK 自适应读取，整体视为单页。"""

    def parse(self, file_path: Path) -> ParseResult:
        text = self._read_text(file_path)
        # txt 无分页概念，全文作为一页（page_texts 仅 1 个元素）
        return ParseResult(text=text, page_texts=[text])

    @staticmethod
    def _read_text(file_path: Path) -> str:
        """按编码候选列表尝试解码，全部失败抛业务异常。"""
        last_error: Exception | None = None
        for encoding in _ENCODINGS:
            try:
                return file_path.read_text(encoding=encoding)
            except UnicodeDecodeError as exc:
                last_error = exc
        raise BizException(f"无法识别的文本编码: {file_path.name}") from last_error
