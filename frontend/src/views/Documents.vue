<script setup lang="ts">
import { onMounted, onUnmounted, ref, watch } from "vue";
import { useRoute } from "vue-router";
import type { UploadFile } from "element-plus";
import { ElMessage, ElMessageBox } from "element-plus";
import { documentApi, kbApi, type DocumentBrief, type DocumentStatus } from "@/api/modules";
import { useKbStore } from "@/stores/kb";
import { formatDateTime, formatSize } from "@/utils/format";
import StatusTag from "@/components/StatusTag.vue";
import ProcessingPipeline from "@/components/ProcessingPipeline.vue";

const route = useRoute();
const kbStore = useKbStore();

const POLL_INTERVAL_MS = 1000;
const POLL_MAX_TIMES = 180; // 最长等待 3 分钟

const selectedKbId = ref<number | null>(null);
const documents = ref<DocumentBrief[]>([]);
const listLoading = ref(false);
const pendingFiles = ref<File[]>([]);
const overwrite = ref(false);
const uploading = ref(false);
/** 当前正在处理后端任务的文档（驱动 Pipeline 卡片） */
const processing = ref<DocumentStatus | null>(null);
let stopPolling = false;

const selectedKb = () => kbStore.list.find((k) => k.id === selectedKbId.value) ?? null;

async function loadKbs(): Promise<void> {
  await kbStore.refresh();
  const fromQuery = Number(route.query.kb_id);
  if (fromQuery && kbStore.list.some((k) => k.id === fromQuery)) {
    selectedKbId.value = fromQuery;
  } else if (kbStore.list.length > 0 && selectedKbId.value === null) {
    selectedKbId.value = kbStore.list[0].id;
  }
}

async function loadDocuments(): Promise<void> {
  if (selectedKbId.value === null) {
    documents.value = [];
    return;
  }
  listLoading.value = true;
  try {
    const detail = await kbApi.detail(selectedKbId.value);
    documents.value = detail.documents;
  } finally {
    listLoading.value = false;
  }
}

watch(selectedKbId, loadDocuments);

function onFileChange(_file: UploadFile, files: UploadFile[]): void {
  const raws: File[] = [];
  files.forEach((f) => {
    if (f.raw) raws.push(f.raw);
  });
  pendingFiles.value = raws;
}

function removePending(raw: File): void {
  pendingFiles.value = pendingFiles.value.filter((f) => f !== raw);
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

/** 轮询文档状态直到终态（2完成/3失败/4降级完成），3 分钟超时兜底；返回最后拿到的状态 */
async function pollUntilDone(fileId: string): Promise<DocumentStatus | null> {
  stopPolling = false;
  let last: DocumentStatus | null = null;
  for (let i = 0; i < POLL_MAX_TIMES && !stopPolling; i++) {
    const status = await documentApi.status(fileId);
    processing.value = status;
    last = status;
    if (status.status === 2 || status.status === 3 || status.status === 4) return status;
    await sleep(POLL_INTERVAL_MS);
  }
  return last;
}

/** 串行上传：一个文档处理到终态后再传下一个，避免同时多个任务抢占 embedding 资源 */
async function startUpload(): Promise<void> {
  const kbId = selectedKbId.value;
  if (kbId === null) {
    ElMessage.warning("请先选择目标知识库");
    return;
  }
  if (pendingFiles.value.length === 0) {
    ElMessage.warning("请先选择文件");
    return;
  }
  uploading.value = true;
  try {
    for (const file of pendingFiles.value) {
      processing.value = null;
      try {
        const uploaded = await documentApi.upload(kbId, file, overwrite.value);
        ElMessage.success(`已入队：${uploaded.original_filename}`);
        const final = await pollUntilDone(uploaded.file_id);
        if (final?.status === 3) {
          ElMessage.error(`「${file.name}」处理失败：${final.parse_error ?? "未知原因"}`);
        } else if (final?.status === 4) {
          ElMessage.warning(`「${file.name}」降级完成，内容可能不完整`);
        } else if (final === null) {
          ElMessage.warning(`「${file.name}」等待超时，请刷新列表查看最终状态`);
        }
      } catch (err) {
        // 单个失败不阻塞队列其余文件；错误提示由 request 拦截器统一弹出
        console.error("[upload] 上传失败", file.name, err);
      }
    }
  } finally {
    uploading.value = false;
    processing.value = null;
    await Promise.all([loadDocuments(), kbStore.refresh()]);
  }
}

async function removeDoc(row: DocumentBrief): Promise<void> {
  try {
    await ElMessageBox.confirm(
      `确认删除文档「${row.original_filename}」？其 Milvus 向量、数据库记录与磁盘文件都会被级联删除，不可恢复。`,
      "删除确认",
      { type: "warning", confirmButtonText: "确认删除", cancelButtonText: "取消" },
    );
  } catch {
    return;
  }
  await documentApi.remove(row.file_id);
  ElMessage.success("已删除");
  await Promise.all([loadDocuments(), kbStore.refresh()]);
}

onMounted(loadKbs);
onUnmounted(() => {
  stopPolling = true;
});
</script>

<template>
  <div>
    <div class="rag-toolbar">
      <span class="rag-page-title">文档</span>
      <div class="spacer" />
      <el-button :loading="listLoading" @click="loadDocuments">刷新</el-button>
    </div>

    <div class="rag-card upload-card">
      <div class="upload-kb-row">
        <span class="upload-kb-label">目标知识库</span>
        <el-select v-model="selectedKbId" placeholder="请选择知识库" style="width: 280px">
          <el-option v-for="kb in kbStore.list" :key="kb.id" :label="kb.name" :value="kb.id" />
        </el-select>
      </div>

      <el-upload
        drag
        multiple
        :auto-upload="false"
        :file-list="[]"
        :on-change="onFileChange"
        :on-remove="(f: any) => removePending(f.raw)"
      >
        <div class="upload-drop-inner">
          <p class="upload-drop-title">拖拽文件到此处，或点击选择</p>
          <p class="upload-drop-hint">支持 txt / md / pdf / docx / xls / 图片等，单文件 ≤20MB；可一次选多个，按顺序处理</p>
        </div>
      </el-upload>

      <div class="upload-actions">
        <el-checkbox v-model="overwrite">
          同名文档在新文档处理成功后替换旧版本
        </el-checkbox>
        <div class="spacer" />
        <span v-if="pendingFiles.length" class="upload-pending-count">已选 {{ pendingFiles.length }} 个文件</span>
        <el-button type="primary" :loading="uploading" :disabled="pendingFiles.length === 0" @click="startUpload">
          开始上传
        </el-button>
      </div>
    </div>

    <!-- 处理中/处理结果：管线可视化 -->
    <div v-if="processing" class="rag-card pipeline-card">
      <div class="pipeline-head">
        <span class="pipeline-title">处理进度：{{ processing.file_id }}</span>
        <StatusTag :status="processing.status" />
      </div>
      <ProcessingPipeline :status="processing.status" :parse-error="processing.parse_error" />
    </div>

    <div class="rag-card">
      <div class="table-head">
        <span>文档列表（{{ selectedKb()?.name ?? "-" }}）</span>
      </div>
      <el-table :data="documents" v-loading="listLoading" empty-text="当前知识库还没有文档">
        <el-table-column label="文件名" min-width="200" show-overflow-tooltip>
          <template #default="{ row }"><b>{{ row.original_filename }}</b></template>
        </el-table-column>
        <el-table-column label="大小" width="100" align="right">
          <template #default="{ row }">{{ formatSize(row.file_size) }}</template>
        </el-table-column>
        <el-table-column label="状态" width="110" align="center">
          <template #default="{ row }">
            <el-tooltip v-if="row.parse_error" :content="row.parse_error" placement="top">
              <span><StatusTag :status="row.status" /></span>
            </el-tooltip>
            <StatusTag v-else :status="row.status" />
          </template>
        </el-table-column>
        <el-table-column label="分块数" width="90" align="right">
          <template #default="{ row }">{{ row.chunk_count }}</template>
        </el-table-column>
        <el-table-column label="解析器" width="110">
          <template #default="{ row }">{{ row.parser_name || "-" }}</template>
        </el-table-column>
        <el-table-column label="上传时间" width="180">
          <template #default="{ row }">{{ formatDateTime(row.created_at) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="100" align="right">
          <template #default="{ row }">
            <el-button link type="danger" @click="removeDoc(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </div>
  </div>
</template>

<style scoped lang="scss">
.spacer {
  flex: 1;
}

.upload-card {
  padding: 16px 18px;

  .upload-kb-row {
    display: flex;
    align-items: center;
    gap: 12px;
    margin-bottom: 14px;
  }

  .upload-kb-label {
    font-size: 13px;
    color: var(--rag-text-secondary);
  }

  .upload-actions {
    display: flex;
    align-items: center;
    gap: 12px;
    margin-top: 14px;
  }

  .upload-pending-count {
    font-size: 12px;
    color: var(--rag-text-secondary);
  }
}

.upload-drop-inner {
  padding: 8px 0;

  .upload-drop-title {
    font-size: 14px;
    color: var(--rag-text);
  }

  .upload-drop-hint {
    margin-top: 4px;
    font-size: 12px;
    color: var(--rag-text-secondary);
  }
}

.pipeline-card {
  .pipeline-head {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 12px;
  }

  .pipeline-title {
    font-size: 14px;
    font-weight: 600;
  }
}

.table-head {
  margin-bottom: 12px;
  font-size: 14px;
  font-weight: 600;
}
</style>
