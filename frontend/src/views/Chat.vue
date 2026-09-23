<script setup lang="ts">
import { computed, nextTick, onMounted, ref, watch } from "vue";
import { ElMessage } from "element-plus";
import type { RetrievalHit } from "@/api/modules";
import { streamChat } from "@/api/chat";
import { useKbStore } from "@/stores/kb";
import MarkdownBlock from "@/components/MarkdownBlock.vue";

interface ChatMessage {
  role: "user" | "assistant";
  content: string;
  /** assistant：本轮引用来源（start 事件） */
  refs?: RetrievalHit[];
  /** assistant：非回答类结束提示（如"未检索到相关资料"） */
  notice?: boolean;
  error?: boolean;
  streaming?: boolean;
}

const kbStore = useKbStore();

const messages = ref<ChatMessage[]>([]);
const input = ref("");
const sending = ref(false);
const kbId = ref<number | null>(null);
const topK = ref(4);
const scrollRef = ref<HTMLElement>();
const abortController = ref<AbortController | null>(null);

/** 抽屉展示的引用来源 */
const drawerVisible = ref(false);
const drawerMsg = ref<ChatMessage | null>(null);

const kbOptions = computed(() => [
  { id: null as number | null, name: "全部知识库" },
  ...kbStore.list.map((kb) => ({ id: kb.id as number | null, name: kb.name })),
]);

const canSend = computed(() => input.value.trim().length > 0 && !sending.value);

function scrollToBottom(): void {
  nextTick(() => {
    const el = scrollRef.value;
    if (el) el.scrollTop = el.scrollHeight;
  });
}

watch(messages, scrollToBottom, { deep: true });

function openRefs(msg: ChatMessage): void {
  drawerMsg.value = msg;
  drawerVisible.value = true;
}

function stopStreaming(): void {
  abortController.value?.abort();
}

function clearChat(): void {
  if (sending.value) stopStreaming();
  messages.value = [];
}

async function send(): Promise<void> {
  const query = input.value.trim();
  if (!query || sending.value) return;

  messages.value.push({ role: "user", content: query });
  const assistant: ChatMessage = { role: "assistant", content: "", streaming: true };
  messages.value.push(assistant);
  input.value = "";
  sending.value = true;
  scrollToBottom();

  let gotDone = false;
  let streamError: unknown = null;
  const controller = new AbortController();
  abortController.value = controller;

  try {
    await streamChat(
      { query, kbId: kbId.value, topK: topK.value },
      {
        onTrace: (trace) => {
          assistant.refs = trace;
        },
        onDelta: (token) => {
          assistant.content += token;
          scrollToBottom();
        },
        onDone: (data) => {
          gotDone = true;
          if (data.code !== 0) {
            assistant.error = true;
            assistant.content = data.msg || "回答生成失败";
          } else if (data.msg && data.msg !== "ok") {
            // 分级兜底的友好提示（无向量重建中/无文档/未检索到），answer 为空
            assistant.notice = true;
            assistant.content = data.msg;
          } else {
            assistant.content = data.answer || assistant.content;
          }
        },
      },
      controller.signal,
    );
  } catch (err) {
    if (controller.signal.aborted) {
      // 用户主动停止：保留已收到的部分回答
      assistant.content += assistant.content ? "\n\n（已停止生成）" : "（已停止生成）";
    } else {
      streamError = err;
    }
  } finally {
    assistant.streaming = false;
    sending.value = false;
    abortController.value = null;
  }

  if (streamError) {
    if (!gotDone) {
      assistant.error = true;
      assistant.content = streamError instanceof Error ? streamError.message : "网络错误，请稍后重试";
    }
    ElMessage.error("问答失败，请查看会话中的错误提示");
  }
  scrollToBottom();
}

onMounted(async () => {
  await kbStore.refresh();
});
</script>

<template>
  <div class="chat-page">
    <div class="rag-card chat-config">
      <div class="config-item">
        <span class="config-label">知识库</span>
        <el-select v-model="kbId" size="default" style="width: 220px">
          <el-option v-for="opt in kbOptions" :key="String(opt.id)" :label="opt.name" :value="opt.id" />
        </el-select>
      </div>
      <div class="config-item">
        <span class="config-label">召回条数 top_k</span>
        <el-slider v-model="topK" :min="1" :max="10" :step="1" show-stops style="width: 140px" />
        <span class="config-value">{{ topK }}</span>
      </div>
      <div class="spacer" />
      <el-button size="default" :disabled="sending" @click="clearChat">清空对话</el-button>
    </div>

    <div ref="scrollRef" class="chat-messages">
      <div v-if="messages.length === 0" class="chat-empty">
        <p class="chat-empty-title">向知识库提问</p>
        <p class="chat-empty-hint">回答基于检索到的文档片段生成，并标注引用来源；资料不足时会明确回答"未找到"</p>
      </div>

      <div v-for="(msg, i) in messages" :key="i" class="chat-row" :class="`is-${msg.role}`">
        <div class="chat-avatar" :class="`is-${msg.role}`">{{ msg.role === "user" ? "我" : "AI" }}</div>
        <div class="chat-bubble" :class="{ 'is-error': msg.error, 'is-notice': msg.notice }">
          <MarkdownBlock v-if="msg.role === 'assistant'" :content="msg.content" />
          <span v-else class="chat-text">{{ msg.content }}</span>
          <span v-if="msg.streaming && msg.content" class="chat-cursor" />
          <div v-if="msg.role === 'assistant' && msg.refs && msg.refs.length > 0 && !msg.streaming" class="chat-refs">
            <el-button link type="primary" size="small" @click="openRefs(msg)">
              引用 {{ msg.refs.length }} 条来源，点击查看
            </el-button>
          </div>
        </div>
      </div>
    </div>

    <div class="chat-input-area rag-card">
      <el-input
        v-model="input"
        type="textarea"
        :rows="3"
        resize="none"
        placeholder="输入问题，Enter 发送，Shift+Enter 换行"
        :disabled="sending"
        @keydown.enter.exact.prevent="send"
      />
      <div class="chat-actions">
        <el-button v-if="sending" @click="stopStreaming">停止生成</el-button>
        <el-button v-else type="primary" :disabled="!canSend" @click="send">发送</el-button>
      </div>
    </div>

    <!-- 引用来源抽屉：完整内容 + 相似度 + 页码 -->
    <el-drawer v-model="drawerVisible" title="引用来源" size="420px">
      <div v-for="hit in drawerMsg?.refs ?? []" :key="hit.idx" class="ref-card">
        <div class="ref-head">
          <span class="ref-name">[来源{{ hit.idx }}] {{ hit.doc_name }}</span>
          <el-tag size="small" type="info">相似度 {{ hit.similarity.toFixed(4) }}</el-tag>
        </div>
        <div class="ref-meta">页码：{{ hit.page ?? "未知" }}</div>
        <div class="ref-content">{{ hit.content }}</div>
      </div>
      <div v-if="(drawerMsg?.refs ?? []).length === 0" class="ref-empty">本轮没有引用来源</div>
    </el-drawer>
  </div>
</template>

<style scoped lang="scss">
.chat-page {
  display: flex;
  flex-direction: column;
  height: calc(100vh - var(--rag-header-height) - 48px);
}

.chat-config {
  display: flex;
  align-items: center;
  gap: var(--rag-space-6);
  padding: 10px 16px;
  margin-bottom: var(--rag-space-4);

  .config-item {
    display: flex;
    align-items: center;
    gap: 10px;
  }

  .config-label {
    font-size: 13px;
    color: var(--rag-text-secondary);
    white-space: nowrap;
  }

  .config-value {
    font-size: 13px;
    font-weight: 600;
    width: 18px;
  }
}

.spacer {
  flex: 1;
}

.chat-messages {
  flex: 1;
  overflow-y: auto;
  padding: var(--rag-space-2) 0;
}

.chat-empty {
  text-align: center;
  padding-top: 12vh;
  color: var(--rag-text-secondary);

  .chat-empty-title {
    font-size: 18px;
    font-weight: 600;
    color: var(--rag-text);
    margin-bottom: 8px;
  }

  .chat-empty-hint {
    font-size: 13px;
  }
}

.chat-row {
  display: flex;
  gap: 12px;
  margin-bottom: var(--rag-space-4);

  &.is-user {
    flex-direction: row-reverse;
  }
}

.chat-avatar {
  flex: 0 0 34px;
  width: 34px;
  height: 34px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 12px;
  font-weight: 600;

  &.is-user {
    background: var(--rag-primary-soft);
    color: var(--rag-primary);
  }

  &.is-assistant {
    background: var(--rag-surface-soft);
    color: var(--rag-text-secondary);
    border: 1px solid var(--rag-border);
  }
}

.chat-bubble {
  position: relative;
  max-width: 72%;
  padding: 10px 14px;
  border-radius: var(--rag-radius-card);
  background: var(--rag-surface);
  border: 1px solid var(--rag-border);

  &.is-error {
    border-color: var(--rag-danger);
    color: var(--rag-danger);
  }

  &.is-notice {
    border-color: var(--rag-warning);
    background: rgba(207, 139, 0, 0.06);
    color: var(--rag-warning);
  }
}

.chat-text {
  white-space: pre-wrap;
  word-break: break-word;
  line-height: 1.8;
}

.chat-cursor {
  display: inline-block;
  width: 2px;
  height: 14px;
  margin-left: 2px;
  vertical-align: -2px;
  background: var(--rag-primary);
  animation: blink 1s infinite;
}

.chat-refs {
  margin-top: 8px;
  padding-top: 8px;
  border-top: 1px dashed var(--rag-border);
}

.chat-input-area {
  padding: 12px 14px;

  .chat-actions {
    display: flex;
    justify-content: flex-end;
    margin-top: 8px;
  }
}

.ref-card {
  border: 1px solid var(--rag-border);
  border-radius: var(--rag-radius-control);
  padding: 10px 12px;
  margin-bottom: 12px;
  background: var(--rag-surface-soft);

  .ref-head {
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: 8px;
    margin-bottom: 6px;
  }

  .ref-name {
    font-size: 13px;
    font-weight: 600;
  }

  .ref-meta {
    font-size: 12px;
    color: var(--rag-text-secondary);
    margin-bottom: 6px;
  }

  .ref-content {
    font-size: 13px;
    line-height: 1.7;
    max-height: 220px;
    overflow-y: auto;
    white-space: pre-wrap;
    word-break: break-word;
  }
}

.ref-empty {
  color: var(--rag-text-secondary);
  font-size: 13px;
  text-align: center;
  padding-top: 40px;
}

@keyframes blink {
  50% { opacity: 0; }
}
</style>
