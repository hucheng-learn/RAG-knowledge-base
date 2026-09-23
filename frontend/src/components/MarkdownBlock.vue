<script setup lang="ts">
import { computed } from "vue";
import { marked } from "marked";
import DOMPurify from "dompurify";

const props = defineProps<{ content: string }>();

/** Markdown → 安全 HTML：LLM 输出必须经 DOMPurify 消毒后 v-html，防 XSS */
const html = computed(() => {
  if (!props.content) return "";
  const raw = marked.parse(props.content, { async: false }) as string;
  return DOMPurify.sanitize(raw);
});
</script>

<template>
  <div class="md-body" v-html="html" />
</template>

<style scoped lang="scss">
.md-body {
  font-size: 14px;
  line-height: 1.8;
  word-break: break-word;

  :deep(p) {
    margin: 0 0 8px;

    &:last-child {
      margin-bottom: 0;
    }
  }

  :deep(pre) {
    background: var(--rag-surface-soft);
    border: 1px solid var(--rag-border);
    border-radius: var(--rag-radius-control);
    padding: 10px 12px;
    overflow-x: auto;
    font-size: 13px;
  }

  :deep(code) {
    font-family: Consolas, Monaco, monospace;
  }

  :deep(ul), :deep(ol) {
    padding-left: 20px;
    margin: 0 0 8px;
  }

  :deep(table) {
    border-collapse: collapse;
    margin: 8px 0;

    th, td {
      border: 1px solid var(--rag-border);
      padding: 4px 10px;
    }
  }

  :deep(a) {
    color: var(--rag-primary);
  }
}
</style>
