<script setup lang="ts">
import { computed } from "vue";

/** 文档处理状态：0待处理 1处理中 2完成 3失败 4降级完成（与后端 documents.status 对齐） */
const props = defineProps<{ status: number }>();

const map: Record<number, { type: "info" | "warning" | "success" | "danger"; text: string }> = {
  0: { type: "info", text: "待处理" },
  1: { type: "warning", text: "处理中" },
  2: { type: "success", text: "已完成" },
  // 降级完成独立于失败：内容可用但可能不完整（如 MinerU 失败回退 pdfplumber），需要醒目提示
  4: { type: "warning", text: "降级完成" },
  3: { type: "danger", text: "失败" },
};

const meta = computed(() => map[props.status] ?? { type: "info", text: "未知状态" });
</script>

<template>
  <el-tag :type="meta.type" size="small" effect="light">{{ meta.text }}</el-tag>
</template>
