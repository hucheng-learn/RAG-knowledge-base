<script setup lang="ts">
import { computed } from "vue";
import { useRoute } from "vue-router";

const route = useRoute();
const title = computed(() => (route.meta.title as string) ?? "");
</script>

<template>
  <header class="app-header">
    <h1 class="app-header-title">{{ title }}</h1>
    <div class="app-header-actions">
      <el-link href="/docs" target="_blank" type="primary" :underline="false">API 文档</el-link>
    </div>
  </header>
</template>

<style scoped lang="scss">
.app-header {
  height: var(--rag-header-height);
  flex-shrink: 0;
  background: var(--rag-surface);
  border-bottom: 1px solid var(--rag-border);
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 var(--rag-space-6);
}

.app-header-title {
  font-size: 16px;
  font-weight: 600;
}
</style>
