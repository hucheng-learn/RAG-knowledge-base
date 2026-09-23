<script setup lang="ts">
import { onMounted, ref } from "vue";
import { ElMessage } from "element-plus";
import { retrievalApi, type RetrievalTestResult } from "@/api/modules";
import { useKbStore } from "@/stores/kb";

const kbStore = useKbStore();

const query = ref("");
const kbId = ref<number | null>(null);
const topK = ref(4);
const loading = ref(false);
const result = ref<RetrievalTestResult | null>(null);

const kbOptions = () => [
  { id: null as number | null, name: "全部知识库" },
  ...kbStore.list.map((kb) => ({ id: kb.id as number | null, name: kb.name })),
];

async function runTest(): Promise<void> {
  const q = query.value.trim();
  if (!q) {
    ElMessage.warning("请输入测试问题");
    return;
  }
  loading.value = true;
  try {
    result.value = await retrievalApi.test(q, kbId.value, topK.value);
  } finally {
    loading.value = false;
  }
}

onMounted(async () => {
  await kbStore.refresh();
});
</script>

<template>
  <div>
    <div class="rag-toolbar">
      <span class="rag-page-title">检索测试</span>
    </div>

    <div class="rag-card test-card">
      <div class="test-config">
        <span class="config-label">知识库</span>
        <el-select v-model="kbId" style="width: 240px">
          <el-option v-for="opt in kbOptions()" :key="String(opt.id)" :label="opt.name" :value="opt.id" />
        </el-select>
        <span class="config-label">top_k</span>
        <el-slider v-model="topK" :min="1" :max="10" :step="1" show-stops style="width: 140px" />
        <span class="config-value">{{ topK }}</span>
      </div>
      <el-input
        v-model="query"
        type="textarea"
        :rows="2"
        resize="none"
        placeholder="输入测试问题，只检索不生成，直接查看召回的 chunk 与相似度"
        @keydown.enter.exact.prevent="runTest"
      />
      <div class="test-actions">
        <el-button type="primary" :loading="loading" @click="runTest">检索</el-button>
      </div>
    </div>

    <div v-if="loading" class="rag-card result-card" v-loading="loading" style="min-height: 120px" />

    <template v-else-if="result">
      <div class="rag-card result-card">
        <div class="result-head">
          <span>命中 {{ result.hits.length }} 条 / top_k={{ result.top_k }}</span>
          <div class="timing">
            <el-tag size="small" type="info">embedding {{ result.embedding_ms }} ms</el-tag>
            <el-tag size="small" type="info">检索 {{ result.retrieval_ms }} ms</el-tag>
            <el-tag size="small">合计 {{ result.total_ms }} ms</el-tag>
          </div>
        </div>
        <div v-if="result.hits.length === 0" class="result-empty">
          未检索到相关资料（相似度低于阈值或范围内没有文档）
        </div>
        <div v-for="hit in result.hits" :key="hit.idx" class="hit-card">
          <div class="hit-head">
            <span class="hit-name">[来源{{ hit.idx }}] {{ hit.doc_name }}</span>
            <el-tag size="small" :type="hit.similarity >= 0.6 ? 'success' : 'info'">
              相似度 {{ hit.similarity.toFixed(4) }}
            </el-tag>
          </div>
          <div class="hit-meta">页码：{{ hit.page ?? "未知" }}</div>
          <div class="hit-content">{{ hit.content }}</div>
        </div>
      </div>

      <div class="rag-card note-card">
        <p>说明：当前检索为 <b>dense-only 单路 ANN</b>（bge-m3 1024 维向量 + Milvus HNSW + COSINE），命中已按
        <b>相似度阈值</b>过滤；相似度即余弦相似度，可直接用于判断"这条内容是否真的相关"。</p>
        <p>本页不走 LLM 生成，用于验证检索质量与调参（换问题 / 换 top_k / 换知识库对比召回）。</p>
      </div>
    </template>
  </div>
</template>

<style scoped lang="scss">
.test-card {
  padding: 14px 16px;
  margin-bottom: var(--rag-space-4);

  .test-config {
    display: flex;
    align-items: center;
    gap: 10px;
    margin-bottom: 12px;
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

  .test-actions {
    display: flex;
    justify-content: flex-end;
    margin-top: 10px;
  }
}

.result-card {
  padding: 14px 16px;
  margin-bottom: var(--rag-space-4);

  .result-head {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 12px;
    font-size: 13px;
    font-weight: 600;
  }

  .timing {
    display: flex;
    gap: 6px;
    font-weight: 400;
  }
}

.result-empty {
  color: var(--rag-text-secondary);
  text-align: center;
  padding: 24px 0;
  font-size: 13px;
}

.hit-card {
  border: 1px solid var(--rag-border);
  border-radius: var(--rag-radius-control);
  padding: 10px 12px;
  margin-bottom: 10px;
  background: var(--rag-surface-soft);

  &:last-child {
    margin-bottom: 0;
  }

  .hit-head {
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: 8px;
    margin-bottom: 6px;
  }

  .hit-name {
    font-size: 13px;
    font-weight: 600;
  }

  .hit-meta {
    font-size: 12px;
    color: var(--rag-text-secondary);
    margin-bottom: 6px;
  }

  .hit-content {
    font-size: 13px;
    line-height: 1.7;
    max-height: 200px;
    overflow-y: auto;
    white-space: pre-wrap;
    word-break: break-word;
  }
}

.note-card {
  padding: 12px 16px;
  font-size: 12px;
  color: var(--rag-text-secondary);
  line-height: 1.8;

  p {
    margin: 0;
  }
}
</style>
