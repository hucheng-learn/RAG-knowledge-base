import { defineStore } from "pinia";
import { ref } from "vue";
import { kbApi, type KnowledgeBase } from "@/api/modules";

/** 知识库列表全局缓存：文档上传 / 问答范围选择等页面共用 */
export const useKbStore = defineStore("kb", () => {
  const list = ref<KnowledgeBase[]>([]);
  const loading = ref(false);

  async function refresh(): Promise<void> {
    loading.value = true;
    try {
      list.value = await kbApi.list();
    } finally {
      loading.value = false;
    }
  }

  function nameOf(id: number | null | undefined): string {
    if (id == null) return "";
    return list.value.find((k) => k.id === id)?.name ?? `#${id}`;
  }

  return { list, loading, refresh, nameOf };
});
