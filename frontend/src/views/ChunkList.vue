<script setup lang="ts">
import { computed, nextTick, onMounted, ref, watch } from "vue";
import { useRoute } from "vue-router";
import { Refresh } from "@element-plus/icons-vue";
import { chunksApi, kbApi, type ChunkItem, type DocumentBrief, type DocumentChunksResult } from "@/api/modules";
import { useKbStore } from "@/stores/kb";
import { formatSize } from "@/utils/format";
import StatusTag from "@/components/StatusTag.vue";

/**
 * Chunk 查看器（P1）：原文 ↔ Chunk ↔ Metadata 可追溯。
 * 入口：文档页「查看分块」、问答/检索来源卡片「定位分块」（?doc_id=&hl=&kb_id=）。
 * 数据源：GET /api/v1/documents/{file_id}/chunks
 */
const route = useRoute();
const kbStore = useKbStore();

/** 文档 status=2 先于向量回写（_persist 置 2 → insert → _mark_vectorized），刚完成的文档可能短暂显示待嵌入 */
const EMBEDDING_LABELS: Record<number, { text: string; type: "info" | "success" | "danger" }> = {
  0: { text: "待嵌入", type: "info" },
  1: { text: "已嵌入", type: "success" },
  2: { text: "嵌入失败", type: "danger" },
};

const selectedKbId = ref<number | null>(null);
const documents = ref<DocumentBrief[]>([]);
const selectedDocId = ref<string | null>(null);
const result = ref<DocumentChunksResult | null>(null);
const loading = ref(false);
const docsLoading = ref(false);

// 过滤与展开状态
const keyword = ref("");
const embedFilter = ref<"all" | "1" | "0">("all");
const expandedIndexes = ref<Set<number>>(new Set());
const hlIndex = ref<number | null>(null);

const selectedDoc = computed(() =>
  documents.value.find((d) => d.file_id === selectedDocId.value) ?? null,
);

const visibleChunks = computed<ChunkItem[]>(() => {
  if (!result.value) return [];
  const kw = keyword.value.trim().toLowerCase();
  return result.value.chunks.filter((c) => {
    if (embedFilter.value === "1" && c.embedding_status !== 1) return false;
    if (embedFilter.value === "0" && c.embedding_status !== 0) return false;
    if (kw && !c.content.toLowerCase().includes(kw)) return false;
    return true;
  });
});

async function loadKbs(): Promise<void> {
  await kbStore.refresh();
  const kbFromQuery = Number(route.query.kb_id);
  if (kbFromQuery && kbStore.list.some((k) => k.id === kbFromQuery)) {
    selectedKbId.value = kbFromQuery;
  } else if (kbStore.list.length > 0 && selectedKbId.value === null) {
    selectedKbId.value = kbStore.list[0].id;
  }
}

async function loadDocuments(): Promise<void> {
  if (selectedKbId.value === null) {
    documents.value = [];
    return;
  }
  docsLoading.value = true;
  try {
    const detail = await kbApi.detail(selectedKbId.value);
    documents.value = detail.documents;
  } finally {
    docsLoading.value = false;
  }
}

async function loadChunks(): Promise<void> {
  const fileId = selectedDocId.value;
  if (!fileId) {
    result.value = null;
    return;
  }
  loading.value = true;
  try {
    result.value = await chunksApi.byDoc(fileId);
  } finally {
    loading.value = false;
  }
}

/** 带 doc_id 直达时：优先用 kb_id 入参，否则遍历知识库找到该文档所属库 */
async function resolveTargetDoc(): Promise<void> {
  const docId = typeof route.query.doc_id === "string" ? route.query.doc_id : null;
  const hl = Number(route.query.hl);
  hlIndex.value = Number.isFinite(hl) && route.query.hl !== undefined ? hl : null;
  if (!docId) {
    // 无直达入参：默认选中文档列表第一个，便于直接浏览
    if (documents.value.length > 0) selectedDocId.value = documents.value[0].file_id;
    await loadChunks();
    return;
  }
  if (kbStore.list.some((k) => k.id === selectedKbId.value) &&
      documents.value.some((d) => d.file_id === docId)) {
    selectedDocId.value = docId;
    await loadChunks();
    return;
  }
  for (const kb of kbStore.list) {
    const detail = await kbApi.detail(kb.id);
    if (detail.documents.some((d) => d.file_id === docId)) {
      selectedKbId.value = kb.id;
      documents.value = detail.documents;
      selectedDocId.value = docId;
      await loadChunks();
      return;
    }
  }
  selectedDocId.value = docId; // 找不到归属也照查（404 由接口提示）
  await loadChunks();
}

function isExpanded(chunk: ChunkItem): boolean {
  if (hlIndex.value === chunk.chunk_index) return true;
  return expandedIndexes.value.has(chunk.chunk_index);
}

function isLong(chunk: ChunkItem): boolean {
  return chunk.content.length > 120 || chunk.content.includes("\n");
}

function toggleExpand(chunk: ChunkItem): void {
  const next = new Set(expandedIndexes.value);
  if (next.has(chunk.chunk_index)) next.delete(chunk.chunk_index);
  else next.add(chunk.chunk_index);
  expandedIndexes.value = next;
}

watch(selectedKbId, async () => {
  await loadDocuments();
  selectedDocId.value = documents.value[0]?.file_id ?? null;
  await loadChunks();
});

watch(selectedDocId, loadChunks);

watch(
  () => route.query,
  async () => {
    if (route.path !== "/chunks") return;
    await loadKbs();
    await loadDocuments();
    await resolveTargetDoc();
    scrollToHighlight();
  },
);

async function scrollToHighlight(): Promise<void> {
  if (hlIndex.value === null) return;
  await nextTick();
  document.getElementById(`chunk-${hlIndex.value}`)?.scrollIntoView({ behavior: "smooth", block: "center" });
}

onMounted(async () => {
  await loadKbs();
  await loadDocuments();
  await resolveTargetDoc();
  scrollToHighlight();
});
</script>

<template>
  <div>
    <div class="rag-toolbar">
      <span class="rag-page-title">分块查看</span>
      <div class="spacer" />
      <el-button :loading="loading" :icon="Refresh" @click="loadChunks">刷新</el-button>
    </div>

    <div class="rag-card picker-card">
      <div class="picker-row">
        <span class="picker-label">知识库</span>
        <el-select v-model="selectedKbId" placeholder="请选择知识库" style="width: 260px" :loading="kbStore.loading">
          <el-option v-for="kb in kbStore.list" :key="kb.id" :label="kb.name" :value="kb.id" />
        </el-select>
        <span class="picker-label">文档</span>
        <el-select
          v-model="selectedDocId"
          placeholder="请选择文档"
          style="width: 320px"
          :loading="docsLoading"
          :disabled="documents.length === 0"
        >
          <el-option
            v-for="doc in documents"
            :key="doc.file_id"
            :label="`${doc.original_filename}（${formatSize(doc.file_size)}）`"
            :value="doc.file_id"
          />
        </el-select>
      </div>
      <div class="picker-hint">
        查看文档的原始分块与元数据：检查切片质量、对比页码/类型/标题层级，排查"为什么这段话召回了/没召回"。刚处理完成文档的向量回写有秒级窗口，可点右上角刷新。
      </div>
    </div>

    <!-- 文档信息条 -->
    <div v-if="result" class="rag-card doc-info-card">
      <div class="doc-info-head">
        <b>{{ result.doc_name }}</b>
        <StatusTag :status="result.status" />
      </div>
      <div class="doc-info-meta">
        <el-tag size="small" type="info">解析器：{{ result.parser_name || "-" }}</el-tag>
        <el-tag size="small">分块 {{ result.chunk_count }}</el-tag>
        <el-tag size="small" :type="result.embedded_count === result.chunk_count ? 'success' : 'warning'">
          已嵌入 {{ result.embedded_count }} / {{ result.chunk_count }}
        </el-tag>
      </div>
    </div>

    <div v-if="result && result.chunks.length > 0" class="rag-card">
      <div class="filter-row">
        <el-input v-model="keyword" placeholder="按内容关键字过滤分块" clearable style="width: 280px" />
        <el-select v-model="embedFilter" style="width: 140px">
          <el-option label="全部状态" value="all" />
          <el-option label="已嵌入" value="1" />
          <el-option label="未嵌入" value="0" />
        </el-select>
        <span class="filter-count">显示 {{ visibleChunks.length }} / {{ result.chunks.length }} 块</span>
      </div>

      <div v-loading="loading">
        <div
          v-for="chunk in visibleChunks"
          :id="`chunk-${chunk.chunk_index}`"
          :key="chunk.chunk_index"
          class="chunk-card"
          :class="{ 'is-highlight': hlIndex === chunk.chunk_index }"
        >
          <div class="chunk-card-head">
            <span class="chunk-index">#{{ chunk.chunk_index }}</span>
            <el-tag v-if="chunk.block_type" size="small" type="info" effect="plain">{{ chunk.block_type }}</el-tag>
            <span class="chunk-meta">第 {{ chunk.page_number }} 页</span>
            <span v-if="chunk.token_count" class="chunk-meta">{{ chunk.token_count }} tokens</span>
            <div class="spacer" />
            <el-tag size="small" :type="EMBEDDING_LABELS[chunk.embedding_status]?.type ?? 'info'">
              {{ EMBEDDING_LABELS[chunk.embedding_status]?.text ?? chunk.embedding_status }}
            </el-tag>
          </div>
          <div v-if="chunk.heading_path.length > 0" class="chunk-heading">
            <span v-for="(h, i) in chunk.heading_path" :key="i" class="chunk-heading-item">{{ h }}</span>
          </div>
          <div class="chunk-content" :class="{ expanded: isExpanded(chunk) }">{{ chunk.content }}</div>
          <div v-if="isLong(chunk)" class="chunk-card-foot">
            <el-button link type="primary" @click="toggleExpand(chunk)">
              {{ isExpanded(chunk) ? "收起" : "展开全文" }}
            </el-button>
            <span v-if="chunk.vector_id" class="chunk-vector">vector_id: {{ chunk.vector_id }}</span>
          </div>
        </div>
        <el-empty v-if="visibleChunks.length === 0" description="没有符合过滤条件的分块" :image-size="60" />
      </div>
    </div>

    <el-empty
      v-else-if="result && result.chunks.length === 0"
      class="rag-card"
      description="该文档还没有分块（可能尚未处理完成）"
    />
    <el-empty v-else-if="!result" class="rag-card" description="选择知识库与文档后查看分块" />
  </div>
</template>

<style scoped lang="scss">
.spacer {
  flex: 1;
}

.picker-card {
  padding: 16px 18px;

  .picker-row {
    display: flex;
    align-items: center;
    gap: 12px;
    flex-wrap: wrap;
  }

  .picker-label {
    font-size: 13px;
    color: var(--rag-text-secondary);
  }

  .picker-hint {
    margin-top: 10px;
    font-size: 12px;
    line-height: 1.6;
    color: var(--rag-text-secondary);
  }
}

.doc-info-card {
  padding: 14px 18px;

  .doc-info-head {
    display: flex;
    align-items: center;
    gap: 10px;
    margin-bottom: 8px;
    font-size: 14px;
  }

  .doc-info-meta {
    display: flex;
    gap: 8px;
    flex-wrap: wrap;
  }
}

.filter-row {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 14px;

  .filter-count {
    font-size: 12px;
    color: var(--rag-text-secondary);
  }
}

.chunk-card {
  border: 1px solid var(--rag-border);
  border-radius: var(--rag-radius-control);
  padding: 12px 14px;
  margin-bottom: 10px;
  background: var(--rag-surface);

  &.is-highlight {
    border-color: var(--rag-primary);
    box-shadow: 0 0 0 1px var(--rag-primary-soft);
  }

  .chunk-card-head {
    display: flex;
    align-items: center;
    gap: 8px;
    margin-bottom: 6px;
  }

  .chunk-index {
    font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
    font-size: 13px;
    font-weight: 700;
    color: var(--rag-primary);
  }

  .chunk-meta {
    font-size: 12px;
    color: var(--rag-text-secondary);
  }

  .chunk-heading {
    display: flex;
    flex-wrap: wrap;
    gap: 4px 8px;
    margin-bottom: 6px;
    font-size: 12px;
    color: var(--rag-text-secondary);

    .chunk-heading-item + .chunk-heading-item::before {
      content: "›";
      margin-right: 8px;
      color: var(--rag-border);
    }
  }

  .chunk-content {
    font-size: 13px;
    line-height: 1.7;
    white-space: pre-wrap;
    word-break: break-all;
    display: -webkit-box;
    -webkit-box-orient: vertical;
    -webkit-line-clamp: 3;
    line-clamp: 3;
    overflow: hidden;

    &.expanded {
      display: block;
      -webkit-line-clamp: unset;
      line-clamp: unset;
    }
  }

  .chunk-card-foot {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-top: 4px;

    .chunk-vector {
      font-size: 11px;
      color: var(--rag-text-secondary);
      font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
    }
  }
}
</style>
