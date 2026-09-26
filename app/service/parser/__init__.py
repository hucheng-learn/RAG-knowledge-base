"""文档解析器子包：通过 DocumentParser 抽象屏蔽解析器差异。

对外只暴露 `get_parser()` 工厂，按文件后缀名返回解析器实例：

- **纯文本类**（`.txt` / `.md`）→ 轻量原生解析器（无需外部服务）；
- **PDF**（`.pdf`）→ 由 `.env` 的 `PDF_PARSER` 决定：`pdfplumber`（基线）或 `mineru`；
  选 `mineru` 时自动包一层**降级**（MinerU 失败回退 pdfplumber）；
- **复杂格式**（`.doc/.docx/.ppt/.pptx/.xls/.xlsx`）与**图片**（`.png/.jpg/.jpeg`）
  → 本地 MinerU 结构化解析（MinerU 由 DocVortex 提供多格式解析能力）。

新增格式：写解析器类 → 在 `_TEXT_PARSERS` 或 `_MINERU_EXTENSIONS` 登记 → 上层零改动。
"""

from app.config.settings import get_settings
from app.service.parser.base import DocumentBlock, DocumentParser, ParseResult
from app.service.parser.fallback_parser import FallbackDocumentParser
from app.service.parser.mineru_parser import MinerUParser
from app.service.parser.pdf_parser import PdfParser
from app.service.parser.txt_parser import TxtParser
from app.utils.exceptions import BizException

__all__ = [
    "DocumentBlock",
    "DocumentParser",
    "ParseResult",
    "FallbackDocumentParser",
    "MinerUParser",
    "PdfParser",
    "TxtParser",
    "get_parser",
]

# 纯文本格式 → 原生轻量解析
_TEXT_PARSERS: dict[str, type[DocumentParser]] = {
    ".txt": TxtParser,
    ".md": TxtParser,
}

# 复杂二进制格式与图片 → 本地 MinerU 结构化解析
_MINERU_EXTENSIONS: frozenset[str] = frozenset({
    ".doc", ".docx", ".ppt", ".pptx", ".xls", ".xlsx",
    ".png", ".jpg", ".jpeg",
})


def get_parser(extension: str) -> DocumentParser:
    """按文件后缀名获取解析器实例。

    Args:
        extension: 小写后缀名（含点，如 ".pdf"）。

    Raises:
        BizException: 没有注册对应解析器。
    """
    parser_cls = _TEXT_PARSERS.get(extension)
    if parser_cls is not None:
        return parser_cls()

    if extension == ".pdf":
        # 使用 MinerU 时包一层降级解析器，避免服务故障导致 PDF 无法入库。
        if get_settings().pdf_parser == "mineru":
            return FallbackDocumentParser(MinerUParser(), PdfParser())
        return PdfParser()

    if extension in _MINERU_EXTENSIONS:
        return MinerUParser()

    raise BizException(f"没有对应的解析器: {extension}")
