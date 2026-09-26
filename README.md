# 企业知识库 RAG

基于 FastAPI、Vue 3、MySQL 和 Milvus 的本地部署知识库。支持文档异步解析入库、向量检索、流式问答和检索结果溯源。文档解析与 Embedding 在本地运行；LLM 可配置为 DeepSeek API 或本地 Ollama。

## 功能

- 知识库与文档管理，支持同名文档显式覆盖和级联删除。
- 上传任务异步处理，支持状态查询、失败重试和向量重建。
- 文本、PDF、Office 文档和图片解析；PDF 支持 pdfplumber 与本地 MinerU，并可降级解析。
- 基于 bge-m3 与 Milvus 的向量检索；MySQL 保存文档、分块和任务元数据。
- SSE 流式 RAG 问答、来源展示、独立检索测试和分块追溯。
- Vue 前端由 FastAPI 同源托管，生产构建产物已包含在 `app/static/`。

## 快速启动

### 本地运行后端

```powershell
conda activate rag_kb
pip install -r requirements.txt
Copy-Item .env.example .env
```

按 `.env` 配置数据库、Milvus、Embedding 模型路径和 LLM。启动 MySQL 与 Milvus（或使用本机已有服务），然后运行：

```powershell
docker compose -f deploy/docker-compose.yml up -d milvus
uvicorn app.main:app --reload
```

若使用本地 MinerU，设置 `PDF_PARSER=mineru` 并启动解析服务：

```powershell
docker compose -f deploy/docker-compose.yml up -d mineru
```

### Docker 全栈

全栈 Compose 包含 MySQL、Milvus、MinerU、Ollama 和后端。模型权重需预先放在宿主机，或通过 `deploy/.env` 设置 `OLLAMA_MODELS_HOST_PATH` 和 `EMBEDDING_MODEL_HOST_PATH`。首次部署需要准备 Compose 中引用的本地镜像标签，详细步骤见 [`deploy/README.md`](deploy/README.md)。

```powershell
docker compose -f deploy/docker-compose.yml up -d --build
docker compose -f deploy/docker-compose.yml ps
```

访问 <http://127.0.0.1:8000/>；API 文档为 <http://127.0.0.1:8000/docs>，健康检查为 <http://127.0.0.1:8000/health>。

## API

| 方法 | 路径 | 用途 |
|---|---|---|
| `POST` | `/api/v1/kbs` | 创建知识库 |
| `GET` | `/api/v1/kbs`、`/api/v1/kbs/{id}` | 查询知识库 |
| `DELETE` | `/api/v1/kbs/{id}` | 删除知识库及其文档 |
| `POST` | `/api/v1/documents/upload?kb_id=&overwrite=false` | 上传并排队处理文档 |
| `GET` | `/api/v1/documents/{file_id}/status` | 查询处理状态 |
| `GET` | `/api/v1/documents/{file_id}/chunks` | 查看文档分块与嵌入状态 |
| `DELETE` | `/api/v1/documents/{file_id}` | 删除文档及关联数据 |
| `POST` | `/api/v1/chat` | SSE 流式问答 |
| `POST` | `/api/v1/retrieval/test` | 只检索并返回命中片段与耗时 |

## 前端

源码位于 `frontend/`，使用 Vue 3、TypeScript、Vite 和 Element Plus。页面包括知识库、文档、问答、检索测试和分块查看。

```powershell
cd frontend
npm install
npm run dev
npm run build:static
```

`build:static` 会将构建结果同步到 `app/static/`。该目录是运行时静态资源，直接改前端源码后应重新构建，不要手改生成文件。

## 文档格式

| 格式 | 解析方式 |
|---|---|
| TXT、Markdown | 内置文本解析 |
| PDF | pdfplumber 或本地 MinerU；MinerU 不可用或无文本时回退到 pdfplumber |
| DOC、DOCX、PPT、PPTX、XLS、XLSX、PNG、JPG | 本地 MinerU |

上传扩展名白名单和模型、服务配置见 `.env.example`。容器部署、镜像和模型挂载说明见 [`deploy/README.md`](deploy/README.md)；当前架构与关键设计见 [`docs/TECH_DESIGN.md`](docs/TECH_DESIGN.md)。

## 目录

- `app/`：FastAPI 应用、数据模型、解析、分块、检索和任务处理。
- `app/static/`：由前端构建生成并随项目部署的静态文件。
- `frontend/`：前端源码。
- `deploy/`：Docker Compose 与部署指南。
- `docs/TECH_DESIGN.md`：系统架构与关键设计说明。
- `scripts/`：数据库校验、Milvus 检查和向量重建工具。
- `sql/schema.sql`：数据库表结构。
- `tests/`：解析与稳定性回归测试。
