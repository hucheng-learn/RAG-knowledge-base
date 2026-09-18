"""轻量 token 数估算。

不同 LLM 的 tokenizer 不完全一致；本项目不把云端 tokenizer 拉入运行时，
因此这里使用保守估算做输入保护和统计，不把估算值当作计费精确值。
"""

import math
import re


_ASCII_WORD = re.compile(r"[A-Za-z0-9_]+")


def estimate_token_count(text: str) -> int:
    """估算中英文混合文本 token 数：中文/非 ASCII 字符按 1，英文按 4 字符/词元。"""
    if not text:
        return 0
    non_ascii = sum(1 for char in text if ord(char) > 127)
    ascii_chars = sum(len(match.group(0)) for match in _ASCII_WORD.finditer(text))
    ascii_tokens = math.ceil(ascii_chars / 4) if ascii_chars else 0
    punctuation = sum(
        1 for char in text
        if not char.isspace() and ord(char) < 128 and not char.isalnum() and char != "_"
    )
    return non_ascii + ascii_tokens + punctuation
