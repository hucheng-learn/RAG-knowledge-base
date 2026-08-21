"""PDF 解析器：pdfplumber 逐页提取文本。

设计要点：
1. pdfplumber 基于 pdfminer.six，对复杂排版（表格、多栏）的文本
   还原质量优于 PyPDF2（后者已进入维护模式）；
2. 扫描版 PDF 判定：全部页面都提取不到文本（无文本层）→ 业务异常；
   部分页面无文本（如封面、纯图片页）→ 记 WARNING 继续，容忍 30%；
3. 页间用双换行分隔拼接全文，保留段落/分页语义，方便后续分块。
"""

from pathlib import Path

import pdfplumber

from app.service.parser.base import DocumentParser, ParseResult
from app.utils.exceptions import BizException
from app.utils.logger import get_logger

logger = get_logger(__name__)

# 无文本页占比超过该值记 WARNING（封面/目录等少量空页属正常）
_SCANNED_TOLERANCE_RATIO = 0.3


class PdfParser(DocumentParser):
    """PDF 解析：pdfplumber 逐页提取文字，含扫描版检测。"""

    def parse(self, file_path: Path) -> ParseResult:
        page_texts: list[str] = []
        try:
            # pdfplumber.open 返回上下文管理器，with 块结束自动关闭文件
            with pdfplumber.open(file_path) as pdf:
                for page in pdf.pages:
                    # extract_text() 提取不到文字时返回 None，统一转空串
                    page_texts.append(page.extract_text() or "")
        except BizException:
            raise
        except Exception as exc:
            # 文件损坏/加密等系统级问题：打完整堆栈，转业务异常给用户
            logger.exception("PDF 解析失败: %s", file_path.name)
            raise BizException(f"PDF 解析失败（文件可能已损坏或加密）: {file_path.name}") from exc

        self._check_scanned(file_path, page_texts)
        # 页间双换行拼接（分块时以此为段落边界）
        text = "\n\n".join(page_texts)
        return ParseResult(text=text, page_texts=page_texts)

    @staticmethod
    def _check_scanned(file_path: Path, page_texts: list[str]) -> None:
        """扫描版检测：全页无文本 → 业务异常；部分空页 → WARNING。"""
        if not page_texts:
            raise BizException(f"PDF 没有可解析的页面: {file_path.name}")

        total_chars = sum(len(t.strip()) for t in page_texts)
        if total_chars == 0:
            # 所有页面都无文本层 → 扫描版（图片型 PDF）
            raise BizException(
                f"暂不支持扫描版 PDF: {file_path.name}（无文本层，"
                "请上传可复制文本的 PDF）"
            )

        empty_pages = sum(1 for t in page_texts if not t.strip())
        empty_ratio = empty_pages / len(page_texts)
        if empty_ratio > _SCANNED_TOLERANCE_RATIO:
            logger.warning(
                "PDF 无文本页占比 %.0f%%: %s",
                empty_ratio * 100, file_path.name,
            )
