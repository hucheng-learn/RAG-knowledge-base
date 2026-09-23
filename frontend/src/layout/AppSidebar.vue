<script setup lang="ts">
import { computed } from "vue";
import { useRoute } from "vue-router";
import { ChatDotRound, Collection, DocumentCopy, Search } from "@element-plus/icons-vue";

const route = useRoute();
// hash 路由下取一级路径作为菜单选中态
const active = computed(() => `/${(route.path.split("/")[1] ?? "knowledge-base").toLowerCase()}`);

const menus = [
  { path: "/knowledge-base", title: "知识库", icon: Collection },
  { path: "/documents", title: "文档", icon: DocumentCopy },
  { path: "/chat", title: "AI 助手", icon: ChatDotRound },
  { path: "/retrieval", title: "检索测试", icon: Search },
];
</script>

<template>
  <aside class="app-sidebar">
    <div class="app-logo">
      <span class="app-logo-mark">RAG</span>
      <div class="app-logo-text">
        <strong>知识库工作台</strong>
        <small>Enterprise Knowledge Base</small>
      </div>
    </div>

    <el-menu :default-active="active" router class="app-menu">
      <el-menu-item v-for="m in menus" :key="m.path" :index="m.path">
        <el-icon><component :is="m.icon" /></el-icon>
        <span>{{ m.title }}</span>
      </el-menu-item>
    </el-menu>

    <div class="app-sidebar-foot">本地部署 · On-Premises</div>
  </aside>
</template>

<style scoped lang="scss">
.app-sidebar {
  width: var(--rag-sidebar-width);
  flex-shrink: 0;
  background: var(--rag-surface);
  border-right: 1px solid var(--rag-border);
  display: flex;
  flex-direction: column;
}

.app-logo {
  display: flex;
  align-items: center;
  gap: var(--rag-space-3);
  height: var(--rag-header-height);
  padding: 0 var(--rag-space-4);
  border-bottom: 1px solid var(--rag-border);
}

.app-logo-mark {
  width: 32px;
  height: 32px;
  border-radius: var(--rag-radius-control);
  background: var(--rag-primary);
  color: #fff;
  font-size: 12px;
  font-weight: 700;
  display: inline-flex;
  align-items: center;
  justify-content: center;
}

.app-logo-text {
  display: flex;
  flex-direction: column;
  line-height: 1.2;

  strong {
    font-size: 14px;
  }

  small {
    font-size: 11px;
    color: var(--rag-text-secondary);
  }
}

.app-menu {
  flex: 1;
  border-right: none;
  background: transparent;
  padding: var(--rag-space-2);

  :deep(.el-menu-item) {
    border-radius: var(--rag-radius-control);
    margin-bottom: 2px;
    color: var(--rag-text);
  }

  :deep(.el-menu-item.is-active) {
    color: var(--rag-primary);
    background: var(--rag-primary-soft);
    font-weight: 600;
  }

  :deep(.el-menu-item:hover) {
    background: var(--rag-surface-soft);
  }
}

.app-sidebar-foot {
  padding: var(--rag-space-3) var(--rag-space-4);
  border-top: 1px solid var(--rag-border);
  font-size: 12px;
  color: var(--rag-text-secondary);
}
</style>
