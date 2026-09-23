import type { RetrievalHit } from "./modules";

/** SSE 事件回调 */
export interface ChatStreamHandlers {
  onTrace: (trace: RetrievalHit[]) => void;
  onDelta: (token: string) => void;
  onDone: (data: { code: number; msg: string; answer: string; token_count: number }) => void;
}

export interface ChatParams {
  query: string;
  kbId: number | null;
  topK: number;
}

/**
 * RAG 问答 SSE 客户端（axios 无法消费流式响应，用原生 fetch + ReadableStream）。
 * 事件协议：start(溯源数组) → delta(回答增量) → done(结束/错误码)。
 * 注意：与后端一致，流式接口不走 {code,msg,data} 信封。
 */
export async function streamChat(
  params: ChatParams,
  handlers: ChatStreamHandlers,
  signal: AbortSignal,
): Promise<void> {
  const resp = await fetch("/api/v1/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ query: params.query, kb_id: params.kbId ?? undefined, top_k: params.topK }),
    signal,
  });
  if (!resp.ok || !resp.body) {
    throw new Error(`问答请求失败：HTTP ${resp.status}`);
  }

  const reader = resp.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    let sep = buffer.indexOf("\n\n");
    while (sep >= 0) {
      const block = buffer.slice(0, sep);
      buffer = buffer.slice(sep + 2);
      dispatchBlock(block, handlers);
      sep = buffer.indexOf("\n\n");
    }
  }
  // 流尾残留（无 \n\n 结尾的容错）
  if (buffer.trim()) {
    dispatchBlock(buffer, handlers);
  }
}

/** 解析单个 SSE 块："event: xxx\ndata: {...}" */
function dispatchBlock(block: string, handlers: ChatStreamHandlers): void {
  let event = "";
  const dataLines: string[] = [];
  for (const line of block.split("\n")) {
    if (line.startsWith("event:")) {
      event = line.slice(6).trim();
    } else if (line.startsWith("data:")) {
      dataLines.push(line.slice(5).trim());
    }
  }
  if (!event || dataLines.length === 0) return;
  let data: any;
  try {
    data = JSON.parse(dataLines.join("\n"));
  } catch {
    console.warn("[chat] SSE data 解析失败:", dataLines.join("\n"));
    return;
  }
  if (event === "start") handlers.onTrace(data as RetrievalHit[]);
  else if (event === "delta") handlers.onDelta(String(data));
  else if (event === "done") handlers.onDone(data);
}
