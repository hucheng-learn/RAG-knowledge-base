# 全栈容器部署

`docker-compose.yml` 会启动 MySQL、Milvus（etcd + MinIO + standalone）、MinerU、Ollama 和后端。
模型全部读取**宿主机已有的本地权重**：不需要联网下载，也不需要 `ollama pull`。

## 前置条件

1. **Docker Desktop 已启动**（WSL2 后端）；GPU 机器需已能在容器内使用 NVIDIA GPU（本项目的 MinerU 镜像运行方式见 `mineru/README.md`）；
2. **本地已有 `mineru:4` 镜像**（约 39.9GB，构建方式见 `mineru/README.md`）；
3. **宿主机已备好两份模型权重**，默认路径如下（相对本文件上溯两级即工作区根目录）：

   | 用途 | 默认宿主路径 | 内容 |
   | --- | --- | --- |
   | Ollama LLM | `<工作区>/models` | `manifests/registry.ollama.ai/library/qwen3/{8b,latest}` + `blobs/`（qwen3:8b，约 4.9GB） |
   | Embedding | `<工作区>/bge-m3` | sentence-transformers 目录（`pytorch_model.bin` / tokenizer / `1_Pooling/` 等，约 4.3GB，1024 维） |

   模型放在别的目录时，用环境变量覆盖（**建议写绝对路径**）。compose 的变量插值只读 `deploy/.env` 与当前 shell 环境变量——`RAG-project/.env` 是**应用**配置，不参与 compose 插值（已实测确认）：

   ```dotenv
   # deploy/.env（可选，不放也能用默认路径）
   OLLAMA_MODELS_HOST_PATH=D:\models\ollama
   EMBEDDING_MODEL_HOST_PATH=D:\models\bge-m3
   ```

4. 首次运行要从 docker.io 拉取基础镜像（`mysql` / `etcd` / `minio` / `milvus` / `ollama`）：**需要代理**；后端镜像自身的基础镜像走 DaoCloud + 清华 PyPI，不需要代理。

## 构建 + 启动

```powershell
cd D:\program_data\deepseek\RAG-project（选自己项目的目录）

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

启动后：

- 前端页面：<http://127.0.0.1:8000/>；健康检查：<http://127.0.0.1:8000/health>
- MinerU 首次启动要等 vLLM warmup（约 2~3 分钟），期间 PDF 上传会自动降级到 pdfplumber，不会失败。

## 验证模型确实来自本地

```powershell
# Ollama：应列出 qwen3:8b（来自宿主 models 目录，不是 pull 下来的）
docker compose -f deploy/docker-compose.yml exec ollama ollama list

# 后端：应输出 /models/bge-m3 cpu（容器内生效配置）
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

`backend` 占宿主 8000，与宿主直接跑 `uvicorn` 冲突：只想要依赖服务时**指定服务名**，例如 `up -d milvus`（Milvus 的 `depends_on` 会一并带起 etcd/minio）、`up -d mineru`，不要连 `backend` 一起起。旧版独立 compose（`docker-compose.milvus.yml` / `docker-compose.mineru.yml`）及其 bind 数据目录 `deploy/volumes/` 已删除（2026-09-18，释放约 165MB），因此不再存在"两套栈端口冲突、切换前先 down 另一方"的问题。

覆盖端口与模型路径：在 `deploy/.env` 里写 `BACKEND_HOST_PORT` / `MINERU_HOST_PORT` / `MILVUS_HOST_PORT` / `OLLAMA_HOST_PORT` / `MYSQL_HOST_PORT` / `OLLAMA_MODELS_HOST_PATH` / `EMBEDDING_MODEL_HOST_PATH` / `TZ`，或直接作为 shell 环境变量传入。

## 资源与已知限制

- 统一 compose 用**命名卷**，首次启动是空库：MySQL 表由后端启动时 `create_all` 自动建，Milvus collection 首次入库时惰性创建；**换过数据卷（`down -v`、卷被删）后旧向量不会被带过来**，历史文档需要重新上传（或对 MySQL 里仍有 chunks 的文档跑 `scripts/rebuild_vectors.py`）。旧独立 compose 的 bind 数据（`deploy/volumes/`）已于 2026-09-18 删除；
- **Embedding 走 GPU**（`EMBEDDING_DEVICE=cuda`，backend 服务已预留 GPU 设备）：镜像内的 torch 是 `2.14.0+cu130`，实测在 RTX 5080 Laptop（sm_120 / capability 12.0）上 `torch.cuda.is_available()=True`，**不需要替换 torch 底座**（旧结论"镜像内是 CPU 版 torch"已作废）。预热后对照：批量 512 条 GPU 1.42s / CPU 15.9s、单条 GPU 12.8ms / CPU 447ms（约 11~35 倍），模型常驻约 2.2GB 显存；显存紧张时在 `deploy/.env` 写 `EMBEDDING_DEVICE=cpu` 即可退回 CPU；
- **三个容器共用一张显卡（Ollama + MinerU + backend）**：Ollama 常驻 qwen3:8b 约 5.6GB、bge-m3 约 2.2GB，MinerU 首次解析 PDF/图片时 vLLM warmup 还会一次性预占数 GB（16GB 卡上偏紧）。显存不足时按优先级让出：先删 `ollama:` 服务的 `deploy.resources` 段（Ollama 走 CPU），或给 MinerU 降档，最后才是把 `EMBEDDING_DEVICE` 改回 `cpu`；
- 模型目录是 Windows bind mount，首次加载 qwen3:8b 会比镜像内层慢一些；`OLLAMA_KEEP_ALIVE` 默认已设为 `30m`，避免间隔稍长就重新加载。

## 常见问题

**上传后文档状态 `failed`，`last_error` 是 `collection not found[database=default][collection=doc_chunks]`**

Milvus 换了数据卷（切栈、`down -v`、数据卷被删）后集合不存在，异步任务在解析前"清理重试残留"这一步就抛异常，重试 3 次后文档终态失败、分块数为 0。v1.39 起该步骤已幂等（无集合 → 跳过删除）且改为先 `ensure_collection()` 再清理，任务会自愈，重新上传即可。

旧版本或已进入 `failed` 终态的任务，手工恢复两步：

```powershell
# 1）补建集合（等价于后端的 ensure_collection，用宿主 conda 环境执行）
cd D:\program_data\deepseek\RAG-project
conda activate rag_kb
python -c "from app.service.vector_service import ensure_collection; ensure_collection()"

# 2）把失败任务重新入队（MySQL 在容器的 3307 端口；attempts 归零以重置重试次数）
#    update document_tasks set status=0, attempts=0, next_run_at=now(), locked_at=null, last_error=null where id=<task_id>;
#    update documents set status=0, parse_error=null where id=<doc_id>;
#    worker 会在下个轮询周期（默认 1s）自动领取并重新解析入库
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
docker exec rag-mysql mysql -uroot -p123456 -e "select @@system_time_zone, now();"
```

注意：TZ 只影响**新写入**的时间，已按 UTC 落库的历史行不会被回改，看起来仍会早 8 小时。

**在容器里看日志，还是看项目的 `logs/`？**

两者不是同一份拷贝、也不能互相替代：`logs/` 由 compose 以 `../logs:/app/logs` 挂进容器，所以容器内 `/app/logs/app.log` 和宿主 `logs/app.log` **是同一个文件**（应用自己的日志写这里，带 `(file.py:42)` 行号、10MB×5 滚动、容器删了仍在）；`docker logs` 是 stdout 通道，独有 uvicorn 访问行（`uvicorn.access` 的 logger 设了 `propagate=False`，不进文件）与容器启动/崩溃的 stderr。定位代码行看 `logs/app.log`，查启动失败/访问量看 `docker logs`。

注意：容器内跑的是**镜像里的代码**，改完源码要 `docker compose -f deploy/docker-compose.yml up -d --build backend` 才生效（源码没有挂进容器）。
