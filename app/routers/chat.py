"""RAG 问答接口：SSE 流式。

注意：流式接口不用 {code,msg,data} 信封，改用 SSE 事件协议
（event: start / delta / done），见 PROJECT_PLAN 6.4。
"""

import json

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from app.models.schemas import ChatRequest
from app.service import rag_service
from app.utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api/v1", tags=["问答"])


@router.post(
    "/chat",
    summary="RAG 问答（SSE 流式）",
    description="SSE 事件：start(溯源) → delta(回答增量) → done(结束)。",
)
async def chat(body: ChatRequest) -> StreamingResponse:
    """RAG 问答：SSE 流式返回回答 + 溯源信息。"""
    return StreamingResponse(
        _sse_stream(body),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            # 关闭反向代理(Nginx)缓冲，保证 token 实时流出
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


async def _sse_stream(body: ChatRequest):
    """把 rag_service 的事件 dict 编码成 SSE 文本流。"""
    try:
        async for evt in rag_service.rag_answer(body.query, body.kb_id, body.top_k):
            yield _format_sse(evt["event"], evt["data"])
    except Exception as exc:
        # 流中途异常：发一个错误 done 事件收尾，避免连接悬挂
        logger.exception("RAG 问答流中断: query=%s", body.query[:50])
        yield _format_sse("done", {"code": 500, "msg": "回答生成失败，请稍后重试"})


def _format_sse(event: str, data) -> str:
    """编码单个 SSE 事件：event: xxx\ndata: json\n\n"""
    payload = json.dumps(data, ensure_ascii=False)
    return f"event: {event}\ndata: {payload}\n\n"
