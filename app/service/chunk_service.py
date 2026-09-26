"""文本分块服务：优先结构化分块，兼容按页滑动窗口。

设计要点：
1. chunk_size：检索粒度。太大语义被平均化、召回不精准、浪费 token；
   太小单块信息量不足。中文场景 300~500 字符为常见甜区。
2. overlap：边界补偿。解决「完整语义被切在块边界」的问题，让相邻块
   共享一段文本；取 chunk_size 的 10%~20%，过大导致冗余召回。
3. 按页分块：页面是文档自然边界，保证每块有唯一的「来源页码」，
   保留每块的来源页码；代价是跨页的句子会被切开。
4. 边界处理：空文本返回空列表；overlap 必须 < chunk_size 且 >= 0，
   否则滑动窗口会死循环（窗口不前进），直接抛业务异常。
"""

from dataclasses import dataclass

from app.config.settings import get_settings
from app.service.parser.base import ParseResult
from app.utils.exceptions import BizException
from app.utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class TextChunk:
    """一个分块：内容、来源位置和结构化溯源信息。"""

    chunk_index: int   # 文档内全局块编号（从 0 开始）
    content: str       # 块文本（清洗后）
    page_number: int   # 来源页码（从 1 开始）
    block_type: str | None = None
    heading_path: list[str] | None = None


def chunk_text(text: str, chunk_size: int, overlap: int) -> list:
    """对单段文本做定长滑动窗口分块，返回块文本列表。

    Args:
        text: 待分块文本。
        chunk_size: 每块最大字符数。
        overlap: 相邻块重叠字符数。

    Returns:
        块文本列表（保持原文顺序）。

    Raises:
        BizException: overlap 不在 [0, chunk_size) 区间。
    """
    if not text:
        return []
    if overlap < 0 or overlap >= chunk_size:
        raise BizException(
            f"分块参数非法: overlap={overlap} 必须满足 0 <= overlap < chunk_size={chunk_size}"
        )

    chunks: list = []
    n = len(text)
    start = 0
    while start < n:
        end = min(start + chunk_size, n)
        chunks.append(text[start:end])
        if end == n:
            break  # 已到文本末尾，收尾退出
        # 窗口向后滑动：新起点 = 当前终点 - overlap；
        # max(..., start+1) 兜底保证至少前进 1 字符（防 overlap 接近 chunk_size 时死循环）
        start = max(end - overlap, start + 1)
    return chunks


def chunk_document(
    parse_result: ParseResult,
    page_texts: list[str] | None = None,
    blocks: list | None = None,
) -> list:
    """分块：有结构块时按结构块切分，否则按页滑窗。

    Args:
        parse_result: 解析结果（含逐页文本 page_texts）。
        page_texts: 可选的分块文本页列表。传入时用于替代解析器原始文本，
            例如使用清洗后的逐页文本；未传入时保持原有行为。
        blocks: 可选的清洗后结构化块。传入非空列表时优先使用，
            每个块保留 block_type 和 heading_path 溯源信息。

    Returns:
        TextChunk 列表，chunk_index 为文档内全局编号。
    """
    settings = get_settings()
    chunks: list = []
    global_index = 0
    source_blocks = parse_result.blocks if blocks is None else blocks
    if source_blocks:
        for block in source_blocks:
            content = (block.content or "").strip()
            if not content:
                continue
            pieces = chunk_text(content, settings.chunk_size, settings.chunk_overlap)
            for piece in pieces:
                chunks.append(
                    TextChunk(
                        chunk_index=global_index,
                        content=piece,
                        page_number=max(block.page_number, 1),
                        block_type=block.block_type,
                        heading_path=list(block.heading_path or []),
                    )
                )
                global_index += 1
        logger.info(
            "结构化分块完成: 原始块=%d, 分块=%d (chunk_size=%d, overlap=%d)",
            len(source_blocks), len(chunks), settings.chunk_size, settings.chunk_overlap,
        )
        return chunks

    # enumerate(start=1)：页码从 1 开始，符合人类阅读习惯
    source_pages = parse_result.page_texts if page_texts is None else page_texts
    for page_idx, page_text in enumerate(source_pages, start=1):
        for piece in chunk_text(page_text, settings.chunk_size, settings.chunk_overlap):
            chunks.append(TextChunk(chunk_index=global_index, content=piece, page_number=page_idx))
            global_index += 1

    logger.info(
        "分块完成: 共 %d 块 (chunk_size=%d, overlap=%d)",
        len(chunks), settings.chunk_size, settings.chunk_overlap,
    )
    return chunks
