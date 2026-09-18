# 企业知识库 RAG 后端系统

基于 FastAPI + Milvus + MySQL 的企业知识库 RAG 后端，配套极简前端页面。

> **开发计划与进度跟踪见** **`docs/PROJECT_PLAN.md`（唯一事实来源）。**
> 技术方案与面试要点见 `docs/TECH_DESIGN.md`；协作约定（含文档同步、分支、下载/网络规则）见 `AGENTS.md`。

## 当前进度

按执行顺序（`8 → 9 → 6 → 10 → 11 → 7`）：

- 第一阶段：项目骨架 + 文件上传解析模块（已完成）
- 第二阶段：文本分块 + MySQL 元数据存储（已完成）
- 第三阶段：Embedding 接入 + Milvus 向量入库（已完成）
- 第四阶段：知识库管理接口 + 文档删除级联（已完成）
- 第五阶段：RAG 问答接口（SSE 流式 + 溯源）+ 前端单页（已完成）
- 第八阶段：本地 MinerU 部署与结构化解析（已完成：多格式支持 + PDF 降级保护）
- **第九阶段：结构化分块、异步入库与解析降级 —— ✅ 已完成**（结构化分块、异步 worker、状态轮询、降级状态、SHA-256/解析缓存、assets manifest 均已接入）
- 第六阶段：工程稳定性优化 —— 🟡 进行中（trace_id、LLM 重试、问题长度保护、进程内限流、RAG 阶段耗时日志已完成）
- 第十阶段：Ollama 本地 LLM 与全链路私有化 —— 待开发
- 第十一阶段：pdfplumber / MinerU 对照实验与面试报告 —— 待开发
- 第七阶段：容器部署 —— 最后做（功能定型后一次完成）

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

# 4. 启动依赖服务
#    - MySQL：本机 MySQL80（需先运行）
#    - Milvus：依赖 Docker
docker compose -f deploy/docker-compose.milvus.yml up -d

# 4.1 （可选）本地 MinerU 解析服务：仅当 .env 里 PDF_PARSER=mineru 时才需要
#     镜像 mineru:4 由 MinerU 仓库 docker/china/Dockerfile 构建，模型权重已打进镜像；
#     服务在 http://127.0.0.1:8001/v1（只绑回环、不出内网），需要 NVIDIA GPU
docker compose -f deploy/docker-compose.mineru.yml up -d
curl.exe http://127.0.0.1:8001/v1/health     # 健康检查
#     注意：容器启动后"第一次"解析要等 vLLM 引擎 warmup（约 2~3 分钟），之后单篇约 3 秒

# 5. 启动服务（本地默认绑定 127.0.0.1:8000）
uvicorn app.main:app --reload
# 如需局域网/其他设备访问，改用：uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

启动后访问：

- **前端页面**：<http://127.0.0.1:8000/> （知识库管理 / 文档上传 / RAG 问答）
- Swagger 文档：<http://127.0.0.1:8000/docs>
- 健康检查：<http://127.0.0.1:8000/health>

## 已提供接口

| 方法     | 路径                                 | 说明                                           |
| ------ | ---------------------------------- | -------------------------------------------- |
| POST   | `/api/v1/documents/upload?kb_id=`  | 上传文档（txt/md/pdf/docx/xls/图片等，单文件 ≤20MB），保存后异步入队 |
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
| `app/`     | 后端代码（config / routers / service / models / utils / static）                              |
| `docs/`    | `PROJECT_PLAN.md`（计划与进度，唯一事实来源）、`TECH_DESIGN.md`（技术方案与面试要点）                             |
| `deploy/`  | `docker-compose.milvus.yml`（Milvus）、`docker-compose.mineru.yml`（MinerU）、`mineru/`（部署说明） |
| `sql/`     | `schema.sql`——三张表建表 SQL（权威版本）                                                           |
| `scripts/` | `verify_schema.py`（ORM↔DB 字段校验）、`rebuild_vectors.py`（向量重建/对账补偿）                         |
| `tests/`   | 回归测试（解析基线等）                                                                             |

## 前端

极简单页已实现：单文件 `app/static/index.html`（原生 HTML/JS，无构建），三个 Tab：
知识库管理（新建/列表/删除，**点「文档」查看库内文档列表并支持单文档删除**）、
文档上传（选库上传显示解析结果，**同库同名文件会被拒绝，防止重复上传**）、
RAG 问答（SSE 流式回答 + 溯源卡片）。
由后端同源托管，启动后直接访问 <http://127.0.0.1:8000/> 即可。

## 支持的文件格式与解析器

| 格式                                  | 解析器             | 说明                                             |
| ----------------------------------- | --------------- | ---------------------------------------------- |
| `.txt` / `.md`                      | 原生轻量解析          | 无需外部服务，UTF-8/GBK 自适应                           |
| `.pdf`                              | `PDF_PARSER` 决定 | `pdfplumber`（基线，默认）或 `mineru`（结构化：标题/段落/表格/页码） |
| `.doc` / `.docx`                    | 本地 MinerU       | 结构化解析，含标题层级与表格                                 |
| `.ppt` / `.pptx` / `.xls` / `.xlsx` | 本地 MinerU       | 由 MinerU（DocVortex）提供解析能力                      |
| `.png` / `.jpg` / `.jpeg`           | 本地 MinerU       | 图片 OCR 识别文字后入库                                 |

- 白名单由 `.env` 的 `ALLOWED_EXTENSIONS` 控制；
- **降级保护**：`PDF_PARSER=mineru` 时若 MinerU 不可用，PDF 会自动回退 `pdfplumber` 并在 `documents.parse_error` 记录降级原因（上传不会失败）；响应里的 `parser_name` / `degraded` 字段会告知实际使用的解析器；
- 使用 MinerU 解析的格式（docx/图片等）需要先启动 MinerU 服务；
- 上传接口已改为异步入队；可通过 `/api/v1/documents/{file_id}/status` 查询处理进度。

## 环境注意

- **Python 环境**：使用 conda 环境 **`rag_kb`**（含 GPU torch）；
- **GPU**：本机 RTX 5080（16GB），`EMBEDDING_DEVICE=cuda`；无独显改 `cpu`；
- **国内网络**：模型走Hugging Face（国内镜像`hf-mirror.com`），也可以选择国内魔搭社区ModelScope（`modelscope.cn`）；GitHub / docker.io / 官方 PyPI(包仓库) 需要本地代理；清华 PyPI、DaoCloud、（阿里 `mirrors.aliyun.com` 实测极慢，勿用于构建）；
- **Docker**：Milvus / MinerU 均依赖 Docker Desktop（需先启动）；两者各自独立 compose，可按需启动。
