<script setup lang="ts">
import { onMounted, reactive, ref } from "vue";
import { useRouter } from "vue-router";
import { ElMessage, ElMessageBox } from "element-plus";
import { kbApi } from "@/api/modules";
import { useKbStore } from "@/stores/kb";
import { formatDateTime } from "@/utils/format";

const router = useRouter();
const kbStore = useKbStore();

const loading = ref(false);
const dialogVisible = ref(false);
const submitting = ref(false);
const form = reactive({ name: "", description: "" });

async function loadList(): Promise<void> {
  loading.value = true;
  try {
    await kbStore.refresh();
  } finally {
    loading.value = false;
  }
}

function openCreate(): void {
  form.name = "";
  form.description = "";
  dialogVisible.value = true;
}

async function submitCreate(): Promise<void> {
  const name = form.name.trim();
  if (!name) {
    ElMessage.warning("请输入知识库名称");
    return;
  }
  submitting.value = true;
  try {
    await kbApi.create(name, form.description.trim() || undefined);
    ElMessage.success(`已创建：${name}`);
    dialogVisible.value = false;
    await loadList();
  } finally {
    submitting.value = false;
  }
}

async function removeKb(id: number, name: string): Promise<void> {
  try {
    await ElMessageBox.confirm(
      `确认删除知识库「${name}」？其下所有文档的向量、数据库记录与磁盘文件都会被级联删除，不可恢复。`,
      "删除确认",
      { type: "warning", confirmButtonText: "确认删除", cancelButtonText: "取消" },
    );
  } catch {
    return; // 用户取消（MessageBox 取消也走 reject，静默返回）
  }
  await kbApi.remove(id);
  ElMessage.success("已删除");
  await loadList();
}

/** 跳到文档页并带上库筛选（对应设计方案 5.3「知识库详情 / 文档」） */
function viewDocuments(id: number): void {
  router.push(`/documents?kb_id=${id}`);
}

onMounted(loadList);
</script>

<template>
  <div>
    <div class="rag-toolbar">
      <span class="rag-page-title">知识库</span>
      <div class="spacer" />
      <el-button :loading="loading" @click="loadList">刷新</el-button>
      <el-button type="primary" @click="openCreate">+ 新建知识库</el-button>
    </div>

    <div class="rag-card">
      <el-table :data="kbStore.list" v-loading="loading" empty-text="还没有知识库，先在上方新建一个">
        <el-table-column label="名称" min-width="180">
          <template #default="{ row }">
            <b>{{ row.name }}</b>
          </template>
        </el-table-column>
        <el-table-column prop="description" label="描述" min-width="220" show-overflow-tooltip>
          <template #default="{ row }">{{ row.description || "-" }}</template>
        </el-table-column>
        <el-table-column prop="doc_count" label="文档数" width="100" align="right" />
        <el-table-column label="创建时间" width="180">
          <template #default="{ row }">{{ formatDateTime(row.created_at) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="200" align="right">
          <template #default="{ row }">
            <el-button link type="primary" @click="viewDocuments(row.id)">文档</el-button>
            <el-button link type="danger" @click="removeKb(row.id, row.name)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <el-dialog v-model="dialogVisible" title="新建知识库" width="480px" :close-on-click-modal="false">
      <el-form label-position="top">
        <el-form-item label="名称（唯一，≤64 字符）" required>
          <el-input v-model="form.name" maxlength="64" show-word-limit placeholder="例如：公司制度知识库" />
        </el-form-item>
        <el-form-item label="描述（可选，≤255 字符）">
          <el-input v-model="form.description" maxlength="255" show-word-limit type="textarea" :rows="3" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="submitting" @click="submitCreate">创建</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped lang="scss">
.spacer {
  flex: 1;
}
</style>
