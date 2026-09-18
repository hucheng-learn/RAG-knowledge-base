"""解析与清洗基线回归测试。"""

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from app.service.chunk_service import chunk_document
from app.service.parser.base import DocumentBlock, ParseResult
from app.service.parser.pdf_parser import PdfParser
from app.utils.clean_text import clean_text
from app.utils.exceptions import BizException


class ParsingBaselineTests(unittest.TestCase):
    """解析-清洗-分块链路的基线回归测试。

    这些用例锁定的都是「不该变」的契约，改动解析器/清洗/分块时必须全绿：
    1. ParseResult 同时保留旧的纯文本字段和新的结构化字段；
    2. 分块用的是清洗后的文本，不是解析器原始输出；
    3. 结构化分块要把 block_type / heading_path 带到每一块上；
    4. 清洗能吃掉解析器常见的噪声字符；
    5. 扫描版 PDF 必须被拦成业务异常。

    依赖用 @patch 打桩（get_settings / pdfplumber.open），不碰真实 .env
    和真实文件，保证离线可跑、结果稳定。
    """

    def test_parse_result_keeps_legacy_and_structured_fields(self):
        """ParseResult 的向后兼容性：老字段（text/page_texts）和新字段（blocks/parser_name）能共存。

        第九阶段引入结构化块后，ParseResult 从「纯文本容器」升级成「纯文本 + 结构块」，
        但上层仍有只读 text/page_texts 的旧代码。这条用例保证改造没有把老字段挤掉
        —— 结构化是叠加，不是替换。
        """
        block = DocumentBlock("table", "| A | B |", 2, heading_path=["章节"])
        result = ParseResult("全文", ["全文"], blocks=[block], parser_name="test")

        self.assertEqual(result.text, "全文")
        self.assertEqual(result.page_texts, ["全文"])
        self.assertEqual(result.blocks[0].block_type, "table")
        self.assertEqual(result.blocks[0].heading_path, ["章节"])
        self.assertEqual(result.parser_name, "test")

    @patch(
        "app.utils.clean_text.get_settings",
        return_value=SimpleNamespace(
            clean_remove_invisible=True,
            clean_collapse_newlines=True,
            clean_collapse_spaces=True,
        ),
    )
    @patch(
        "app.service.chunk_service.get_settings",
        return_value=SimpleNamespace(chunk_size=500, chunk_overlap=50),
    )
    def test_chunks_use_cleaned_page_text(self, _chunk_settings, _clean_settings):
        """按页分块：传入的清洗后文本优先于 ParseResult 原始文本，页码从 1 开始。

        page_texts 参数存在的意义就是让调用方能把「清洗后的逐页文本」喂进来。
        这里故意给原始页文本加首尾空格和多余换行，断言入库的块内容是干净的，
        且两页各自成块、页码连续 —— 防止哪天有人把参数退回成直接用
        parse_result.page_texts（脏文本会污染向量库）。
        """
        result = ParseResult("raw", ["  第一页  ", "第二页\n\n"])
        cleaned_pages = [clean_text(page) for page in result.page_texts]
        chunks = chunk_document(result, cleaned_pages)

        self.assertEqual([chunk.content for chunk in chunks], ["第一页", "第二页"])
        self.assertEqual([chunk.page_number for chunk in chunks], [1, 2])

    @patch(
        "app.service.chunk_service.get_settings",
        return_value=SimpleNamespace(chunk_size=10, chunk_overlap=2),
    )
    def test_structured_chunks_preserve_block_metadata(self, _chunk_settings):
        """结构化分块：优先按块切分，且每块都带上 block_type 和 heading_path。

        chunk_size=10 让第二个块（15 字符）必然被切成 2 片，用来验证
        「一个结构块被切碎后，每一片都继承同一份溯源信息」—— 表格块不参与
        二次切分（短于 chunk_size 保持整块），普通文本被切后仍然全部挂着
        同一个 heading_path。这是第五阶段「来源溯源」能落地的前提。
        """
        blocks = [
            DocumentBlock("table", "A | B", 2, heading_path=["章节", "表格"]),
            DocumentBlock("text", "0123456789ABCDE", 2, heading_path=["章节"]),
        ]
        result = ParseResult("", [], blocks=blocks)
        chunks = chunk_document(result, blocks=blocks)

        self.assertEqual(chunks[0].content, "A | B")
        self.assertEqual(chunks[0].block_type, "table")
        self.assertEqual(chunks[0].heading_path, ["章节", "表格"])
        self.assertEqual([chunk.block_type for chunk in chunks[1:]], ["text", "text"])
        self.assertTrue(all(chunk.heading_path == ["章节"] for chunk in chunks[1:]))

    @patch(
        "app.utils.clean_text.get_settings",
        return_value=SimpleNamespace(
            clean_remove_invisible=True,
            clean_collapse_newlines=True,
            clean_collapse_spaces=True,
        ),
    )
    def test_clean_text_removes_parser_noise(self, _settings):
        """清洗规则的端到端断言：一次输入同时覆盖 CRLF 换行、连续空行、BOM、首尾空格四类噪声。

        输入串是刻意构造的「解析器典型脏输出」：Windows 换行 + 表格/分页留下的
        多个空行 + 藏在中间的 BOM + 首尾空白。期望结果是 A 与 B 之间只隔一个
        空行：换行统一、多余空行压到保留段落语义的双换行、不可见字符清掉、
        整体 trim。用真实正则而非 mock，所以这条同时也在守护 clean_text.py 里
        四条规则的执行顺序。
        """
        self.assertEqual(clean_text("  A\r\n\r\n\r\n B\ufeff  "), "A\n\nB")

    def test_pdf_parser_rejects_empty_pdf(self):
        """扫描版/空 PDF 的拦截：pdfplumber 返回 0 页时必须抛 BizException。

        mock 掉 pdfplumber.open 让 pages=[]，模拟无文本层文件。断言的不是
        「不崩溃」而是「抛业务异常」—— 这是给用户的明确提示（请上传可复制文本
        的 PDF），而不是让它静默产出一个空文档、后续分块得到 0 块。
        用 NamedTemporaryFile 只是为了让 parse() 拿到一个语法合法的路径，
        真正读文件的那步已被 mock 替换。
        """
        parser = PdfParser()
        with tempfile.NamedTemporaryFile(suffix=".pdf") as file:
            with patch("app.service.parser.pdf_parser.pdfplumber.open") as open_pdf:
                open_pdf.return_value.__enter__.return_value.pages = []
                with self.assertRaises(BizException):
                    parser.parse(Path(file.name))


if __name__ == "__main__":
    unittest.main()
