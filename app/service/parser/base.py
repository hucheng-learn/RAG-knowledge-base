"""解析器抽象层。

设计目标：屏蔽不同文件格式的解析差异，上层业务（document_service）
只依赖 DocumentParser 接口，新增格式（docx、OCR 等）只需新增一个
解析器实现，零改动上层代码——这就是「面向接口编程」。

ParseResult 携带逐页文本和结构化块，供分块、检索来源展示使用。
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class DocumentBlock:
    """结构化文档块，供结构化分块和来源溯源使用。"""

    block_type: str
    content: str
    page_number: int
    block_index: int = 0
    heading_path: list[str] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)


class ParseResult:
    """解析结果：兼容纯文本，同时承载结构化块和解析元数据。"""

    def __init__(
        self,
        text: str,
        page_texts: list,
        blocks: list[DocumentBlock] | None = None,
        assets: list[dict] | None = None,
        parser_name: str = "unknown",
        parser_version: str | None = None,
        metadata: dict | None = None,
    ) -> None:
        self.text = text              # 全文（页间以两个换行分隔）
        self.page_texts = page_texts  # 逐页文本列表，顺序即页码（txt 视为单页）
        self.blocks = blocks or []
        self.assets = assets or []
        self.parser_name = parser_name
        self.parser_version = parser_version
        self.metadata = metadata or {}

    def __len__(self) -> int:
        return len(self.text)


class DocumentParser(ABC):
    """文档解析器抽象接口：所有解析器实现 parse() 返回 ParseResult。"""

    @abstractmethod
    def parse(self, file_path: Path) -> ParseResult:
        """解析文件为纯文本。

        Args:
            file_path: 已保存到本地的文件绝对路径。

        Returns:
            ParseResult 包含全文与逐页文本。

        Raises:
            BizException: 业务上不支持的情况（如扫描版 PDF、无法识别编码）。
        """
        raise NotImplementedError
