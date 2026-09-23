# 企业知识库 RAG 后端系统

基于 FastAPI + Milvus + MySQL 的企业知识库 RAG 后端，配套极简前端页面。

> **开发计划与进度跟踪见** **`docs/PROJECT_PLAN.md`（唯一事实来源）。**
> 技术方案与面试要点见 `docs/TECH_DESIGN.md`；协作约定（含文档同步、分支、下载/网络规则）见 `AGENTS.md`。

## 当前进度

按执行顺序（`8 → 9 → 6 → 10 → 7`；第十一阶段延期）：

- 第一阶段：项目骨架 + 文件上传解析模块（已完成）
- 第二阶段：文本分块 + MySQL 元数据存储（已完成）
- 第三阶段：Embedding 接入 + Milvus 向量入库（已完成）
- 第四阶段：知识库管理接口 + 文档删除级联（已完成）
- 第五阶段：RAG 问答接口（SSE 流式 + 溯源）+ 前端单页（已完成）
- 第八阶段：本地 MinerU 部署与结构化解析（已完成：多格式支持 + PDF 降级保护）
- **第九阶段：结构化分块、异步入库与解析降级 —— ✅ 已完成**（结构化分块、异步 worker、状态轮询、降级状态、SHA-256/解析缓存、assets manifest 均已接入）
- **第六阶段：工程稳定性优化 —— ✅ 已完成**（trace_id、LLM 重试、字符/token 输入保护、进程内限流、RAG 阶段耗时日志）
- **第十阶段：Ollama 本地 LLM 与全链路私有化 —— ✅ 已完成**（`LLM_PROVIDER` 切换与 qwen3 原生流式接口）
- 第七阶段：容器部署 —— ✅ 已完成（后端镜像与统一 Compose；Ollama/bge-m3 改为挂载宿主本地模型，离线免下载）
- 第十一阶段：pdfplumber / MinerU 对照实验与面试报告 —— ⏸ 延期，不纳入本轮

> 阶段详情与接续指引见 `docs/PROJECT_PLAN.md`（8.0 总览 / 8.0.1 接续指引）。

## 本地启动

```bash
# 1. 激活虚拟环境（本项目使用 conda 环境 rag_kb，已装 GPU torch）
conda activate rag_kb

# 2. 安装依赖
pip install -r requirements.txt

# 3. 复制环境变量模板为 .env，并按本机实际情况修改：
#    EMBEDDING_MODEL（本地 bge-m3 路径）、EMBEDDING_DEVICE（cuda/cpu）、
#    MYSQL_PASSWORD、LLM_API_KEY；PDF_PARSER 决定 PDF 用 pdfplumber 还是 mineru
copy .env.example .env          # Windows
# cp .env.example .env          # Linux/macOS

# 4. 启动依赖服务（统一 Compose，按需指定服务名；别连 backend 一起起，否则和宿主 8000 冲突）
#    - MySQL：本地开发直接用本机 MySQL80（常驻），或容器版 mysql（宿主 3307）
#    - Milvus：容器 rag-milvus（宿主 19530）；depends_on 会把 etcd/minio 一起带起来
docker compose -f deploy/docker-compose.yml up -d milvus

# 4.1 （可选）本地 MinerU 解析服务：仅当 .env 里 PDF_PARSER=mineru 时才需要
#     镜像 mineru:4 由 MinerU 仓库 docker/china/Dockerfile 构建，模型权重已打进镜像；
#     服务在 http://127.0.0.1:8001/v1（只绑回环、不出内网），需要 NVIDIA GPU
docker compose -f deploy/docker-compose.yml up -d mineru
curl.exe http://127.0.0.1:8001/v1/health     # 健康检查
#     注意：容器启动后"第一次"解析要等 vLLM 引擎 warmup（约 2~3 分钟），之后单篇约 3 秒

# 5. 启动服务（本地默认绑定 127.0.0.1:8000）
uvicorn app.main:app --reload
# 如需局域网/其他设备访问，改用：uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

需要一键启动完整本地栈（Docker）时使用统一 Compose（会启动独立的 MySQL、Milvus、MinerU、Ollama 和后端）。

**前置：宿主机已备好两份本地权重**，compose 直接挂载它们，**不联网下载、不需要 `ollama pull`**：

| 用途 | 默认宿主路径 | 内容 |
| --- | --- | --- |
| Ollama LLM | `<工作区>/models` | Ollama 模型仓库（含 `qwen3:8b`，blobs + manifests） |
| Embedding | `<工作区>/bge-m3` | bge-m3 权重目录（sentence-transformers 格式，1024 维） |

路径不同时用 `OLLAMA_MODELS_HOST_PATH` / `EMBEDDING_MODEL_HOST_PATH` 覆盖（写在 `deploy/.env`，或用 shell 环境变量）。完整说明见 `deploy/README.md`。

```powershell
cd D:\program_data\deepseek\RAG-project
docker compose -f deploy/docker-compose.yml build backend   # 构建后端镜像（可选，up --build 也会构建）
docker compose -f deploy/docker-compose.yml up -d --build   # 构建并启动全栈
docker compose -f deploy/docker-compose.yml ps              # 查看状态（rag-ollama 应为 healthy）
docker compose -f deploy/docker-compose.yml exec ollama ollama list  # 确认 qwen3:8b 来自本地模型仓库
```

同一套 Compose 里 `backend` 与宿主 `uvicorn` 都占 8000：全栈起来后就别再在宿主跑 uvicorn；端口或模型路径冲突时用环境变量 `*_HOST_PORT` / `OLLAMA_MODELS_HOST_PATH` / `EMBEDDING_MODEL_HOST_PATH` 覆盖（写在 `deploy/.env`，仅 compose 插值读它）。

启动后访问：

- **前端页面**：<http://127.0.0.1:8000/> （知识库管理 / 文档上传 / RAG 问答）
- Swagger 文档：<http://127.0.0.1:8000/docs>
- 健康检查：<http://127.0.0.1:8000/health>

## 已提供接口

| 方法     | 路径                                 | 说明                                           |
| ------ | ---------------------------------- | -------------------------------------------- |
| POST   | `/api/v1/documents/upload?kb_id=&overwrite=false`  | 上传文档（txt/md/pdf/docx/xls/图片等，单文件 ≤20MB），保存后异步入队；显式覆盖同名旧文档 |
| GET    | `/api/v1/documents/{file_id}/status` | 查询文档处理状态、任务尝试次数、解析器与错误信息 |
| DELETE | `/api/v1/documents/{file_id}`      | 删除文档（级联清理 Milvus/MySQL/文件）                   |
| POST   | `/api/v1/kbs`                      | 新建知识库                                        |
| GET    | `/api/v1/kbs` / `/api/v1/kbs/{id}` | 知识库列表 / 详情                                   |
| DELETE | `/api/v1/kbs/{id}`                 | 删除知识库（级联清理全部文档）                              |
| POST   | `/api/v1/chat`                     | RAG 问答（SSE 流式：start 溯源 / delta 回答 / done 结束） |

## 目录结构

见 `docs/PROJECT_PLAN.md` 第 5 节。关键目录：

| 路径         | 说明                                                                                      |
| ---------- | --------------------------------------------------------------------------------------- |
| `app/`     | 后端代码（config / routers / service / models / utils / static）                             |
| `frontend/` | 前端源码工程（Vue 3 + TS + Vite + Element Plus；`npm run build:static` 产出到 `app/static/`） |
| `docs/`    | `PROJECT_PLAN.md`（计划与进度，唯一事实来源）、`TECH_DESIGN.md`（技术方案与面试要点）                             |
| `deploy/`  | `docker-compose.yml`（唯一入口：全栈一键启动 + 按服务名单独启动依赖，含本地模型挂载）、`mineru/`（MinerU 镜像构建与部署说明） |
| `sql/`     | `schema.sql`——三张表建表 SQL（权威版本）                                                           |
| `scripts/` | `verify_schema.py`（ORM↔DB 字段校验）、`rebuild_vectors.py`（向量重建/对账补偿）                         |
| `tests/`   | 回归测试（解析基线等）                                                                             |

## 前端

按《企业级RAG知识库 UI/UX 设计方案》重构中：**Vue 3 + Element Plus + Vite** SPA，源码在 [frontend/](frontend/)（Design Tokens、Sidebar + Header 布局、hash 路由），构建产物同步到 `app/static/` 由后端同源托管，访问 <http://127.0.0.1:8000/>。

> 当前进度（v1.46）：脚手架 + 布局已落地，四个 P0 页面（知识库 / 文档 / AI 助手 / 检索测试）分步交付中；`app/static` 暂时仍是旧单页（知识库管理 / 文档上传 / RAG 问答三个 Tab），新页面全量交付后由 `npm run build:static` 一次性替换上线。

前端本地开发（改 `frontend/` 源码后）：

```bash
cd frontend
npm install                 # 依赖走 npmmirror 镜像，国内直连免代理
npm run dev                 # vite dev server（5173，/api 代理到 127.0.0.1:8000）
npm run build:static        # 生产构建并把 dist 覆盖同步到 app/static（产物提交 git）
```

约定：`app/static` 下的构建产物**禁止手改**；Docker 镜像不装 Node，直接 `COPY app ./app` 使用已提交产物；hash 路由无需服务端 404 回退配置。详见 `docs/TECH_DESIGN.md` §15。

## 支持的文件格式与解析器

| 格式                                  | 解析器             | 说明                                             |
| ----------------------------------- | --------------- | ---------------------------------------------- |
| `.txt` / `.md`                      | 原生轻量解析          | 无需外部服务，UTF-8/GBK 自适应                           |
| `.pdf`                              | `PDF_PARSER` 决定 | `pdfplumber`（基线，默认）或 `mineru`（结构化：标题/段落/表格/页码） |
| `.doc` / `.docx`                    | 本地 MinerU       | 结构化解析，含标题层级与表格                                 |
| `.ppt` / `.pptx` / `.xls` / `.xlsx` | 本地 MinerU       | 由 MinerU（DocVortex）提供解析能力                      |
| `.png` / `.jpg` / `.jpeg`           | 本地 MinerU       | 图片 OCR 识别文字后入库                                 |

- 白名单由 `.env` 的 `ALLOWED_EXTENSIONS` 控制；
- **降级保护**：`PDF_PARSER=mineru` 时若 MinerU 不可用**或解析成功但没提取到文本**（如脑图等图形化 PDF 被整页识别成一张图），PDF 会自动回退 `pdfplumber` 并在 `documents.parse_error` 记录降级原因（上传不会失败）；响应里的 `parser_name` / `degraded` 字段会告知实际使用的解析器；
- 使用 MinerU 解析的格式（docx/图片等）需要先启动 MinerU 服务；
- 上传接口已改为异步入队；可通过 `/api/v1/documents/{file_id}/status` 查询处理进度。

## 环境注意

- **Python 环境**：使用 conda 环境 **`rag_kb`**（含 GPU torch）；
- **GPU**：本机 RTX 5080（16GB），`EMBEDDING_DEVICE=cuda`；无独显改 `cpu`；
- **国内网络**：模型走Hugging Face（国内镜像`hf-mirror.com`），也可以选择国内魔搭社区ModelScope（`modelscope.cn`）；GitHub / docker.io / 官方 PyPI(包仓库) 需要本地代理；清华 PyPI、DaoCloud、（阿里 `mirrors.aliyun.com` 实测极慢，勿用于构建）；
- **Docker**：`deploy/docker-compose.yml` 是唯一入口——一键起全栈（模型直接挂载宿主本地目录，离线可用；模型路径由 `OLLAMA_MODELS_HOST_PATH` / `EMBEDDING_MODEL_HOST_PATH` 指定），也可用 `up -d milvus` / `up -d mineru` 只起依赖服务给宿主 uvicorn 用（旧的 Milvus/MinerU 独立 compose 已删除）。Docker Hub 官方源需要代理，Dockerfile 已使用 DaoCloud 基础镜像和清华 PyPI 直连；容器时区统一为 `Asia/Shanghai`（`backend` 与 `mysql` 的 `TZ` 成对设置，只改一边会让同一行内 `created_at` 与 `updated_at` 差 8 小时），可用 `deploy/.env` 覆盖；
- **容器内的推理设备**：Embedding **走 GPU**（compose 默认 `EMBEDDING_DEVICE=cuda`，backend 已预留 GPU 设备；镜像内 torch 是 `2.14.0+cu130`，实测支持 RTX 5080/sm_120，无需换 torch 底座）；Ollama、MinerU、backend 三个容器共用这张卡（约 5.6 + 2.2 + MinerU 数 GB），显存不足时按 `deploy/README.md` 的优先级让出（先关 Ollama 的 GPU 预留，最后才把 Embedding 退回 CPU）。
