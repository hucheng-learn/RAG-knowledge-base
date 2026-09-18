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
    def test_parse_result_keeps_legacy_and_structured_fields(self):
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
        self.assertEqual(clean_text("  A\r\n\r\n\r\n B\ufeff  "), "A\n\nB")

    def test_pdf_parser_rejects_empty_pdf(self):
        parser = PdfParser()
        with tempfile.NamedTemporaryFile(suffix=".pdf") as file:
            with patch("app.service.parser.pdf_parser.pdfplumber.open") as open_pdf:
                open_pdf.return_value.__enter__.return_value.pages = []
                with self.assertRaises(BizException):
                    parser.parse(Path(file.name))


if __name__ == "__main__":
    unittest.main()
