"""文档解析器子包：通过 DocumentParser 抽象屏蔽解析器差异。

对外只暴露 get_parser() 工厂：按文件后缀名返回对应解析器实例。
新增格式时：写一个解析器类 → 在 _PARSERS 注册 → 上层零改动。
"""

from app.service.parser.base import DocumentParser, ParseResult
from app.service.parser.pdf_parser import PdfParser
from app.service.parser.txt_parser import TxtParser
from app.utils.exceptions import BizException

# 后缀名 → 解析器类的注册表（新增格式在此登记）
_PARSERS: dict[str, type[DocumentParser]] = {
    ".txt": TxtParser,
    ".pdf": PdfParser,
}


def get_parser(extension: str) -> DocumentParser:
    """按文件后缀名获取解析器实例。

    Args:
        extension: 小写后缀名（含点，如 ".txt"）。

    Raises:
        BizException: 没有注册对应解析器。
    """
    parser_cls = _PARSERS.get(extension)
    if parser_cls is None:
        raise BizException(f"没有对应的解析器: {extension}")
    return parser_cls()
