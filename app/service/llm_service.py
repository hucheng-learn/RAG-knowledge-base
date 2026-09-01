"""大模型调用：OpenAI 兼容格式 + SSE 流式解析。

设计选择：用 httpx 手动解析 SSE，不依赖 openai SDK。
理由（面试点）：
1. 控制力强：能读到每个原始事件，可区分 DeepSeek 推理模型的
   reasoning_content（推理过程）与 content（回答正文）；
2. DeepSeek v4 这类带推理的模型，流式输出先是 reasoning_content
   后才是 content——这里只透出 content（回答），丢弃推理过程，
   避免把"思考过程"当回答流给前端；
3. httpx 已是依赖，无需新增包。

超时：流式场景首 token 可能较慢，read 给到 120s；connect 10s。
"""

import json
from typing import AsyncIterator

import httpx

from app.config.settings import get_settings
from app.utils.exceptions import SystemException
from app.utils.logger import get_logger

logger = get_logger(__name__)

# 流式超时：连接 10s / 读取 120s（首 token 可能慢）/ 写入 30s / 连接池 10s
_TIMEOUT = httpx.Timeout(connect=10, read=120, write=30, pool=10)


async def stream_chat(
    system_prompt: str,
    user_message: str,
) -> AsyncIterator[str]:
    """流式调用 chat/completions，逐段产出回答正文（不含推理过程）。

    Args:
        system_prompt: 系统提示词。
        user_message: 用户消息（RAG 场景已拼接检索上下文）。

    Yields:
        回答的增量文本片段。

    Raises:
        SystemException: LLM 返回非 200、超时等系统级异常。
    """
    settings = get_settings()
    url = f"{settings.llm_base_url.rstrip('/')}/chat/completions"
    payload = {
        "model": settings.llm_model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ],
        "stream": True,
        "temperature": settings.rag_temperature,
        "max_tokens": settings.rag_max_tokens,
    }
    headers = {
        "Authorization": f"Bearer {settings.llm_api_key}",
        "Content-Type": "application/json",
    }

    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        try:
            async with client.stream("POST", url, json=payload, headers=headers) as resp:
                if resp.status_code != 200:
                    body = (await resp.aread()).decode("utf-8", "ignore")
                    logger.error("LLM 请求失败: status=%s body=%s", resp.status_code, body[:500])
                    raise SystemException(f"大模型服务异常（{resp.status_code}）")

                # 逐行读 SSE：事件以 "data: {...}\n\n" 分隔
                async for line in resp.aiter_lines():
                    if not line.startswith("data:"):
                        continue  # 跳过空行/注释行
                    data = line[len("data:"):].strip()
                    if data == "[DONE]":
                        break  # 流结束标记
                    try:
                        chunk = json.loads(data)
                    except json.JSONDecodeError:
                        continue  # 忽略无法解析的碎片
                    choices = chunk.get("choices") or []
                    if not choices:
                        continue
                    delta = choices[0].get("delta", {}) or {}
                    content = delta.get("content")
                    if content:
                        # 只透出回答正文；reasoning_content 推理过程被丢弃
                        yield content
        except httpx.TimeoutException:
            logger.exception("LLM 请求超时: model=%s", settings.llm_model)
            raise SystemException("大模型请求超时，请稍后重试")
