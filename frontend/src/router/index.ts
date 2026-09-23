import { createRouter, createWebHashHistory } from "vue-router";

// hash 路由：FastAPI StaticFiles(html=True) 只认目录根 index.html，
// 没有 history 模式的 404 回退能力，hash 路由不依赖服务端配置即可用。
const routes = [
  { path: "/", redirect: "/knowledge-base" },
  {
    path: "/knowledge-base",
    name: "knowledge-base",
    component: () => import("@/views/KnowledgeBase.vue"),
    meta: { title: "知识库" },
  },
  {
    path: "/documents",
    name: "documents",
    component: () => import("@/views/Documents.vue"),
    meta: { title: "文档" },
  },
  {
    path: "/chat",
    name: "chat",
    component: () => import("@/views/Chat.vue"),
    meta: { title: "AI 助手" },
  },
  {
    path: "/retrieval",
    name: "retrieval",
    component: () => import("@/views/Retrieval.vue"),
    meta: { title: "检索测试" },
  },
];

export const router = createRouter({
  history: createWebHashHistory(),
  routes,
});
