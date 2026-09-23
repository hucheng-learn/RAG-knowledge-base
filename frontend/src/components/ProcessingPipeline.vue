<script setup lang="ts">
import { computed } from "vue";

/**
 * 文档处理管线可视化。
 * 诚实边界：后端 document_tasks 只暴露文档级状态（0/1/2/3/4），
 * 不暴露细分步骤进度，因此「处理中」时解析→入库组整体高亮，
 * 不伪造每一步的精确进度。
 */
const props = defineProps<{
  status: number;
  parseError?: string | null;
}>();

const steps = computed(() => [
  "上传落盘", "格式校验", "文档解析", "文本清洗", "智能分块", "向量嵌入", "Milvus 写入", "处理完成",
]);

const failed = computed(() => props.status === 3);
const running = computed(() => props.status === 1);
const finished = computed(() => props.status === 2 || props.status === 4);

/** 每个节点的展示状态 */
const nodeStates = computed<string[]>(() => {
  if (finished.value) return steps.value.map(() => "done");
  if (failed.value) return steps.value.map((_, i) => (i <= 1 ? "done" : "error"));
  if (running.value) return steps.value.map((_, i) => (i <= 1 ? "done" : i <= 6 ? "active" : "wait"));
  // status=0 待处理：刚上传成功，排队中
  return steps.value.map((_, i) => (i === 0 ? "done" : i === 1 ? "active" : "wait"));
});
</script>

<template>
  <div class="pipeline">
    <div class="pipeline-track">
      <template v-for="(step, i) in steps" :key="step">
        <div v-if="i > 0" class="pipeline-link" :class="nodeStates[i] === 'wait' ? 'is-wait' : 'is-passed'" />
        <div class="pipeline-node" :class="`is-${nodeStates[i]}`">
          <span class="pipeline-dot" />
          <span class="pipeline-label">{{ step }}</span>
        </div>
      </template>
    </div>
    <p v-if="running" class="pipeline-hint">任务处理中，后端按整体任务状态推进（细分步骤进度不单独暴露）…</p>
    <p v-else-if="failed" class="pipeline-hint is-error">
      处理失败{{ parseError ? `：${parseError}` : "" }}
    </p>
  </div>
</template>

<style scoped lang="scss">
.pipeline {
  padding: 4px 0;

  &-track {
    display: flex;
    align-items: center;
  }

  &-node {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 6px;
    flex: 0 0 auto;
  }

  &-dot {
    width: 14px;
    height: 14px;
    border-radius: 50%;
    background: var(--rag-border);
    transition: background 0.2s;
  }

  &-label {
    font-size: 12px;
    color: var(--rag-text-secondary);
    white-space: nowrap;
  }

  &-link {
    flex: 1;
    height: 2px;
    min-width: 12px;
    margin: 0 4px 18px; /* 上对齐圆点行 */
    border-radius: 1px;
    background: var(--rag-border);

    &.is-passed {
      background: var(--rag-success);
    }
  }

  .is-done .pipeline-dot {
    background: var(--rag-success);
  }
  .is-done .pipeline-label {
    color: var(--rag-success);
  }

  .is-active .pipeline-dot {
    background: var(--rag-primary);
    animation: pulse 1.2s ease-in-out infinite;
  }
  .is-active .pipeline-label {
    color: var(--rag-primary);
    font-weight: 600;
  }

  .is-error .pipeline-dot {
    background: var(--rag-danger);
  }
  .is-error .pipeline-label {
    color: var(--rag-danger);
  }

  &-hint {
    margin: 10px 0 0;
    font-size: 12px;
    color: var(--rag-text-secondary);

    &.is-error {
      color: var(--rag-danger);
    }
  }
}

@keyframes pulse {
  0%, 100% { transform: scale(1); opacity: 1; }
  50% { transform: scale(1.35); opacity: 0.7; }
}
</style>
