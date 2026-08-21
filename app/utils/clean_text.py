"""文本清洗工具。

清洗规则（每项都有 .env 开关，默认全开）：
1. 统一换行符：\r\n / \r → \n（Windows/旧 Mac 文本的兼容）；
2. 去除不可见乱码字符：控制字符、零宽字符、BOM、替换符 U+FFFD；
   保留 \t \n 等排版控制符；
3. 去除每行首尾空白（中文排版中行首行尾空格无意义）；
4. 压缩行内连续空格（2+ → 1）；
5. 压缩连续换行（3+ → 2），保留「段落间一个空行」的语义。

顺序很重要：先统一换行符 → 再去乱码 → 再行内处理 → 最后压缩换行，
否则可能出现「空白行导致 \n 数量虚高、压缩不彻底」的问题。

每次清洗记录前后字符数对比日志，用于排查解析质量。
"""

import logging
import re

from app.config.settings import get_settings

logger = logging.getLogger(__name__)

# 不可见/乱码字符：控制字符（排除 \t=0x09 \n=0x0a \r=0x0d）、
# 零宽字符（U+200B~U+200F）、行分隔符、BOM(U+FEFF)、替换符(U+FFFD)
_INVISIBLE_RE = re.compile(
    r"[\x00-\x08\x0b\x0c\x0e-\x1f\u200b-\u200f\u2028\u2029\ufeff\ufffd]"
)
# 每行首尾空白（MULTILINE 使 ^ $ 匹配每行边界）
_STRIP_LINE_RE = re.compile(r"^[ \t]+|[ \t]+$", re.MULTILINE)
# 行内连续空格/制表符（2+ 个）
_MULTI_SPACE_RE = re.compile(r"[ \t]{2,}")
# 连续换行（3+ 个，含纯空行）→ 双换行
_MULTI_NEWLINE_RE = re.compile(r"\n{3,}")


def clean_text(text: str) -> str:
    """按 .env 配置清洗文本，返回清洗后的文本。

    Args:
        text: 解析器产出的原始文本。

    Returns:
        清洗后的文本。所有开关关闭时原样返回（不损耗数据）。
    """
    settings = get_settings()
    switches = (
        settings.clean_remove_invisible,
        settings.clean_collapse_newlines,
        settings.clean_collapse_spaces,
    )
    if not any(switches):
        return text

    original_len = len(text)
    cleaned = text

    # 1. 统一换行符（必须先做：\r\n 若留到后面，会被当两个字符处理）
    cleaned = cleaned.replace("\r\n", "\n").replace("\r", "\n")

    # 2. 去除不可见乱码字符
    if settings.clean_remove_invisible:
        cleaned = _INVISIBLE_RE.sub("", cleaned)

    # 3. 行首行尾空白
    if settings.clean_collapse_spaces:
        cleaned = _STRIP_LINE_RE.sub("", cleaned)

    # 4. 行内连续空白压缩
    if settings.clean_collapse_spaces:
        cleaned = _MULTI_SPACE_RE.sub(" ", cleaned)

    # 5. 连续换行压缩（3+ → 2，保留段落间空行）
    if settings.clean_collapse_newlines:
        cleaned = _MULTI_NEWLINE_RE.sub("\n\n", cleaned)

    # 6. 整体首尾修剪
    cleaned = cleaned.strip()

    logger.info(
        "文本清洗: %d -> %d 字符 (减少 %d)",
        original_len, len(cleaned), original_len - len(cleaned),
    )
    return cleaned
