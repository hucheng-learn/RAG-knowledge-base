<script setup lang="ts">
import { computed } from "vue";
import { useRoute } from "vue-router";

const route = useRoute();
const title = computed(() => (route.meta.title as string) ?? "");
</script>

<template>
  <div class="rag-card page-placeholder">
    <el-empty :description="`「${title}」页面建设中，后续提交交付`" />
  </div>
</template>

<style scoped lang="scss">
.page-placeholder {
  padding: var(--rag-space-8) 0;
}
</style>
