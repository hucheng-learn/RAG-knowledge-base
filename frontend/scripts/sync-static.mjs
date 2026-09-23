// 构建后把 frontend/dist 同步到 app/static（FastAPI StaticFiles 托管在 /）。
// 约定：app/static 下的构建产物随 git 提交，宿主 uvicorn / Docker 镜像都不需要 Node；
//       改前端源码后必须重新执行 npm run build:static 并一起提交。
import { cp, mkdir, readdir, rm } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const frontendDir = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const distDir = path.join(frontendDir, "dist");
const staticDir = path.resolve(frontendDir, "..", "app", "static");

// 清空目标目录（旧单页 index.html 等历史文件全部移除，保证产物干净、无残留）
for (const entry of await readdir(staticDir)) {
  await rm(path.join(staticDir, entry), { recursive: true, force: true });
}
await mkdir(staticDir, { recursive: true });
await cp(distDir, staticDir, { recursive: true });
console.log(`[sync-static] ${distDir} -> ${staticDir}`);
