# 全栈容器部署

`docker-compose.yml` 会启动 MySQL、Milvus（etcd + MinIO + standalone）、MinerU、Ollama 和后端。
模型全部读取**宿主机已有的本地权重**：不需要联网下载，也不需要 `ollama pull`。

## 前置条件

1. **Docker Desktop 已启动**（WSL2 后端）；使用 MinerU 时，GPU 机器需允许容器访问 NVIDIA GPU；
2. **本地已有 `mineru:4` 镜像**，并按下文生成项目专用标签；
3. **宿主机已备好两份模型权重**，默认路径如下（相对本文件上溯两级即工作区根目录）：

   | 用途 | 默认宿主路径 | 内容 |
   | --- | --- | --- |
   | Ollama LLM | `<工作区>/models` | `manifests/registry.ollama.ai/library/qwen3/{8b,latest}` + `blobs/`（qwen3:8b，约 4.9GB） |
   | Embedding | `<工作区>/bge-m3` | sentence-transformers 目录（`pytorch_model.bin` / tokenizer / `1_Pooling/` 等，约 4.3GB，1024 维） |

   模型放在别的目录时，用环境变量覆盖（**建议写绝对路径**）。Compose 的变量插值读取 `deploy/.env` 与当前 shell 环境变量；项目根目录的 `.env` 用于应用配置：

   ```dotenv
   # deploy/.env（可选，不放也能用默认路径）
   OLLAMA_MODELS_HOST_PATH=D:\models\ollama
   EMBEDDING_MODEL_HOST_PATH=D:\models\bge-m3
   ```

4. 若本地缺少上游镜像，首次从 docker.io / quay.io 拉取 `mysql` / `etcd` / `minio` / `milvus` / `ollama`：**需要代理**；后端镜像自身的基础镜像走 DaoCloud + 清华 PyPI，不需要代理。缺失时先拉取对应版本：

   ```powershell
   docker pull mysql:8.0
   docker pull quay.io/coreos/etcd:v3.5.14
   docker pull minio/minio:RELEASE.2023-03-20T20-16-18Z
   docker pull milvusdb/milvus:v2.4.13
   docker pull ollama/ollama:latest
   ```

## 构建 + 启动

```powershell
cd D:\program_data\deepseek\RAG-project（选自己项目的目录）

# 0）首次部署时给已有的上游镜像添加本地项目标签（不复制镜像层）
docker tag mysql:8.0 rag-mysql:rag-8.0
docker tag quay.io/coreos/etcd:v3.5.14 rag-etcd:rag-v3.5.14
docker tag minio/minio:RELEASE.2023-03-20T20-16-18Z rag-minio:rag-RELEASE.2023-03-20T20-16-18Z
docker tag milvusdb/milvus:v2.4.13 rag-milvus:rag-v2.4.13
docker tag ollama/ollama:latest rag-ollama:rag-latest
docker tag mineru:4 rag-mineru:rag-4

# 1）单独构建后端镜像，便于看清构建日志
docker compose -f deploy/docker-compose.yml build backend

# 2）启动全栈（只有 backend 走 Dockerfile 构建，其余用现成镜像）
docker compose -f deploy/docker-compose.yml up -d

# 2.1）只起依赖服务（宿主用 uvicorn 跑后端时用这种，避免 8000 冲突）
docker compose -f deploy/docker-compose.yml up -d milvus    # 会带起 etcd/minio
docker compose -f deploy/docker-compose.yml up -d mineru    # 仅 PDF_PARSER=mineru 时需要

# 3）查看状态：rag-ollama 显示 healthy 才说明本地 qwen3:8b 已被正确识别
docker compose -f deploy/docker-compose.yml ps
```

Compose 中的运行镜像统一用 `rag-<服务>:rag-<上游版本>`；后端按 `.env` 的应用版本构建为 `rag-backend:rag-0.1.0`。例如 `mysql:8.0` 会增加别名 `rag-mysql:rag-8.0`，`mineru:4` 会增加别名 `rag-mineru:rag-4`。第三方服务设置了 `pull_policy: never`，缺少项目标签时先执行上面的 `docker tag`，避免 Docker 把 `rag-*` 误当作远程仓库拉取。镜像标签与容器名、数据卷相互独立；重新打标签不会迁移或清空数据。

启动后：

- 前端页面：<http://127.0.0.1:8000/>；健康检查：<http://127.0.0.1:8000/health>
- MinerU 首次启动要等 vLLM warmup（约 2~3 分钟），期间 PDF 上传会自动降级到 pdfplumber，不会失败。

## 前端产物随 git 提交（镜像不含 Node）

前端源码在 `frontend/`（Vue 3 + Element Plus + Vite），**构建产物已提交进 git**：`frontend/npm run build:static` 会把 `dist/` 覆盖同步到 `app/static/`，Dockerfile 直接 `COPY app ./app`——**镜像构建不需要 Node、也不需要重新构建前端**。改了前端源码后只需要：

```powershell
cd D:\program_data\deepseek\RAG-project\frontend
npm run build:static    # vite build + 同步覆盖 app/static（产物记得提交 git）
```

页面是 hash 路由（`/#/knowledge-base`、`/#/documents`、`/#/chat`、`/#/retrieval`），StaticFiles 托管无需服务端 404 回退配置。npm 依赖走 npmmirror 镜像直连（免代理）。

## 验证模型确实来自本地

```powershell
# Ollama：应列出 qwen3:8b（来自宿主 models 目录，不是 pull 下来的）
docker compose -f deploy/docker-compose.yml exec ollama ollama list

# 查看后端当前生效的 Embedding 模型、设备和 LLM 配置
docker compose -f deploy/docker-compose.yml exec backend python -c "from app.config.settings import get_settings as g; s=g(); print(s.embedding_model, s.embedding_device, s.llm_model)"
```

## 常用运维命令

```powershell
docker compose -f deploy/docker-compose.yml logs -f backend   # 后端日志
docker compose -f deploy/docker-compose.yml logs -f ollama    # Ollama 日志（显存/加载失败看这里）
docker compose -f deploy/docker-compose.yml stop              # 停止
docker compose -f deploy/docker-compose.yml down              # 删容器与网络（命名卷数据保留）
docker compose -f deploy/docker-compose.yml down -v           # 连命名卷一起删（MySQL/Milvus 数据清零）
```

## 端口与冲突

默认宿主端口：后端 8000、MinerU 8001、MySQL 3307（避开本机 MySQL80 的 3306）、Milvus 19530/9091、MinIO 9000/9001、Ollama 11434。

`backend` 占宿主 8000，与宿主直接运行 `uvicorn` 冲突。只启动依赖服务时指定服务名，例如 `up -d milvus`（会一并启动 etcd 和 MinIO）或 `up -d mineru`。

覆盖端口与模型路径：在 `deploy/.env` 里写 `BACKEND_HOST_PORT` / `MINERU_HOST_PORT` / `MILVUS_HOST_PORT` / `OLLAMA_HOST_PORT` / `MYSQL_HOST_PORT` / `OLLAMA_MODELS_HOST_PATH` / `EMBEDDING_MODEL_HOST_PATH` / `TZ`，或直接作为 shell 环境变量传入。

## 资源与已知限制

- Compose 使用命名卷保存 MySQL 和 Milvus 数据。执行 `down -v` 会清空这些数据；若 MySQL 分块仍在，可用 `scripts/rebuild_vectors.py` 重建 Milvus 向量。
- Embedding 默认使用 GPU（`EMBEDDING_DEVICE=cuda`）；显存不足时可在 `deploy/.env` 设置 `EMBEDDING_DEVICE=cpu`。Ollama、MinerU 和后端可能竞争 GPU 显存。
- 模型目录通过宿主机挂载；首次从 Windows 目录加载模型可能较慢。

## 常见问题

**上传后文档状态 `failed`，`last_error` 是 `collection not found[database=default][collection=doc_chunks]`**

如果更换或清空 Milvus 数据卷后文档处理失败，先确认 collection 已创建，再重新排队处理失败文档。当前 worker 会在清理旧向量前确保 collection 存在；可用 `scripts/rebuild_vectors.py` 从 MySQL 中已有的分块重建向量。

已进入 `failed` 终态的任务，可在 MySQL 中重置任务与文档状态后由 worker 重新处理：

```powershell
# 确认 collection 存在（用项目 Python 环境执行）
python -c "from app.service.vector_service import ensure_collection; ensure_collection()"

# 在 MySQL 中重置失败任务（按实际 task_id 和 doc_id 替换占位符）
#    update document_tasks set status=0, attempts=0, next_run_at=now(), locked_at=null, last_error=null where id=<task_id>;
#    update documents set status=0, parse_error=null where id=<doc_id>;
#    worker 会自动领取任务并重新处理
```

**日志时间（和 `created_at`）比宿主慢 8 小时**

容器默认 UTC，而本项目的代码用 `datetime.now()` 取**进程本地时间**（日志的 `%(asctime)s` 走 `logging`→`time.localtime`，`updated_at` / `next_run_at` 直接 `datetime.now()`），MySQL 侧的 `created_at` / `next_run_at` 默认值则由 `DEFAULT CURRENT_TIMESTAMP` 生成（`time_zone=SYSTEM`，跟随容器时区）。所以 `backend` 与 `mysql` 的 TZ 必须**成对设置**——只改一个，同一行里 `created_at` 和 `updated_at` 就会差 8 小时。compose 已给这两个服务注入 `TZ: ${TZ:-Asia/Shanghai}`：

```dotenv
# deploy/.env（可选，不设即为 Asia/Shanghai）
TZ=Asia/Shanghai
```

改完需重建容器才生效（命名卷数据保留）：

```powershell
docker compose -f deploy/docker-compose.yml up -d mysql backend
docker exec rag-backend date                                   # 应显示 CST
docker exec -it rag-mysql mysql -uroot -p -e "select @@system_time_zone, now();"
```

注意：TZ 只影响**新写入**的时间，已按 UTC 落库的历史行不会被回改，看起来仍会早 8 小时。

**在容器里看日志，还是看项目的 `logs/`？**

两者不是同一份拷贝、也不能互相替代：`logs/` 由 compose 以 `../logs:/app/logs` 挂进容器，所以容器内 `/app/logs/app.log` 和宿主 `logs/app.log` **是同一个文件**（应用自己的日志写这里，带 `(file.py:42)` 行号、10MB×5 滚动、容器删了仍在）；`docker logs` 是 stdout 通道，独有 uvicorn 访问行（`uvicorn.access` 的 logger 设了 `propagate=False`，不进文件）与容器启动/崩溃的 stderr。定位代码行看 `logs/app.log`，查启动失败/访问量看 `docker logs`。

注意：容器内跑的是**镜像里的代码**，改完源码要 `docker compose -f deploy/docker-compose.yml up -d --build backend` 才生效（源码没有挂进容器）。
