"""解析器抽象层。

设计目标：屏蔽不同文件格式的解析差异，上层业务（document_service）
只依赖 DocumentParser 接口，新增格式（docx、OCR 等）只需新增一个
解析器实现，零改动上层代码——这就是「面向接口编程」。

ParseResult 携带 page_texts（逐页文本），为后续分块模块的
「来源页码」溯源功能预留数据（第二阶段使用）。
"""

from abc import ABC, abstractmethod
from pathlib import Path


class ParseResult:
    """解析结果：全文 + 逐页文本。"""

    def __init__(self, text: str, page_texts: list) -> None:
        self.text = text              # 全文（页间以两个换行分隔）
        self.page_texts = page_texts  # 逐页文本列表，顺序即页码（txt 视为单页）

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
