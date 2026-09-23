import { fileURLToPath, URL } from "node:url";
import { defineConfig } from "vite";
import vue from "@vitejs/plugin-vue";

// 构建约定：
// - base './'：产物用相对路径引用，FastAPI StaticFiles 挂任意前缀都能跑
// - 路由用 hash 模式，避免依赖服务端 404 回退（StaticFiles html=True 只认目录根 index.html）
// - 产物目录 frontend/dist，由 scripts/sync-static.mjs 同步到 app/static 后提交
export default defineConfig({
  base: "./",
  plugins: [vue()],
  resolve: {
    alias: { "@": fileURLToPath(new URL("./src", import.meta.url)) },
  },
  build: {
    outDir: "dist",
    emptyOutDir: true,
    chunkSizeWarningLimit: 1600,
  },
  // 仅 `npm run dev`（5173）需要：/api 代理到宿主 uvicorn
  server: {
    port: 5173,
    proxy: {
      "/api": { target: "http://127.0.0.1:8000", changeOrigin: true },
    },
  },
});
