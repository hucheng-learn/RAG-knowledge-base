<script setup lang="ts">
import AppHeader from "./AppHeader.vue";
import AppSidebar from "./AppSidebar.vue";
</script>

<template>
  <div class="app-shell">
    <AppSidebar />
    <div class="app-body">
      <AppHeader />
      <main class="app-content">
        <div class="app-container">
          <router-view />
        </div>
      </main>
    </div>
  </div>
</template>

<style scoped lang="scss">
.app-shell {
  display: flex;
  height: 100vh;
  overflow: hidden;
}

.app-body {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
}

.app-content {
  flex: 1;
  overflow-y: auto;
  padding: var(--rag-space-6);
}

.app-container {
  max-width: var(--rag-content-max);
  margin: 0 auto;
}
</style>
