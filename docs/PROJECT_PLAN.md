# 企业知识库 RAG 后端系统 — 开发计划与进度跟踪

> 开发以本文档为准，任何方案调整都先改这里（在「变更记录」登记），每个阶段完成后更新「进度跟踪」。
>
> 当前版本：v1.39 ｜ 创建日期：2026-08-20 ｜ 最近更新：2026-09-18

---

## 1. 项目概述

开发一个简历可用、偏工业级的企业知识库 RAG 后端系统，配套极简前端页面。

- **背景**：本项目用于面试讲解项目原理。
- **目标**：文档上传 → 解析 → 清洗 → 分块 → 向量化 → 入库；用户提问 → 召回 → 拼上下文 → 大模型 SSE 流式回答 + 溯源。
- **开发方式**：严格按模块分阶段开发，**禁止一次性生成全部代码**，一个模块确认后再进入下一阶段。

### 1.1 部署定位与数据边界

本项目当前的目标交付形态是**客户本地部署（On-Premises）**：企业文档、解析结果、Embedding、向量数据和问答上下文原则上均保留在客户内网，不依赖第三方文档解析 SaaS。

当前开发阶段为了提高验证效率，LLM 暂时使用 DeepSeek API，因此属于“本地数据处理 + 云端生成”的过渡性混合模式。后续使用 Ollama 部署本地 LLM，并确认 Embedding 始终使用本地模型后，形成全链路本地化方案。

核心边界：

- `uploads/` 保存原始上传文件，作为解析、重试、降级和实验复现的数据源；
- MinerU 采用本地部署，不调用 MinerU 公有云 API，不上传企业 PDF；
- `pdfplumber` 保留为轻量基线和 MinerU 故障时的降级解析器；
- 解析、分块、向量化与 LLM 通过接口和配置解耦，便于后续扩展交付模式；
- 当前不提前实现 SaaS、多租户、客户专属云等复杂能力，先完成客户本地部署主线。

后续可基于本项目另拉分支学习其他交付模式：SaaS/公有云 API、客户专属云、混合云、托管私有云、一体机/边缘部署。本阶段只沉淀必要的抽象边界，不为这些模式提前引入额外复杂度。

---

## 2. 技术栈

| 层次 | 选型 | 说明 |
|---|---|---|
| Web 框架 | Python + FastAPI | 异步、Pydantic 强校验、自带 OpenAPI 文档 |
| PDF 解析 | **本地 MinerU**（目标）+ pdfplumber（基线/降级） | MinerU 负责复杂版面、表格、OCR 等结构化解析；pdfplumber 保留轻量回退能力 |
| 文本解析 | 内置 open() 读取 | txt 直接读取 |
| 向量库 | Milvus | 只存 embedding 向量，与 MySQL 元数据一一关联 |
| 元数据库 | MySQL | 知识库、文档、chunk 元数据 |
| Embedding | **bge-m3** | 本地 sentence-transformers 加载，1024 维；|
| 大模型 | 当前 DeepSeek 官方 API；目标 Ollama 本地模型 | 当前用于快速验证，后续切换本地模型完成全链路私有化 |
| ORM | SQLAlchemy 2.x | 配合 MySQL |
| 前端 | 单页 HTML + 原生 JS | FastAPI 静态同源托管（`app/static/`），fetch + ReadableStream 消费 SSE，无构建工具 |
| 配置 | pydantic-settings + .env | 禁止硬编码 |
| 部署 | Docker / docker-compose | 当前目标为客户本地部署；MinerU、后端、Milvus、MySQL、Ollama 逐步纳入本地部署 |

---

## 3. 整体业务流程

### 3.1 文档入库流程

```
文档上传 → `uploads/` 本地持久化 → 文件解析 → 文本清洗 → 结构化分块(chunk)
        → Embedding 生成向量 → 向量存入 Milvus，chunk 元数据存入 MySQL
```

### 3.2 问答流程

```
用户提问 → question 向量化 → Milvus 相似度召回 topN 片段
        → 拼接上下文 Prompt → 请求大模型 → SSE 流式输出回答 + 溯源信息
```

---

## 4. 项目标准分层架构（严格遵守）

| 层 | 职责 | 禁止事项 |
|---|---|---|
| `config` | 配置文件：向量库地址、MySQL 配置、大模型服务地址、embedding 参数、分块默认参数、文件上传配置；用 `.env` 环境变量管理 | 禁止硬编码配置 |
| `routers` | 接口层：定义全部 HTTP 接口，只负责接收参数、调用 service | 不写业务逻辑 |
| `service` | 业务逻辑层：文档解析、文本清洗、分块、向量入库、检索问答全部在此 | — |
| `models` | Pydantic 请求/响应模型、MySQL ORM 表结构定义 | — |
| `utils` | 通用工具：文本清洗工具、全局日志、异常处理、文件工具 | — |
| `static` | 前端单页（`index.html`，三个 Tab），由 FastAPI 同源托管在 `/` | 不写后端逻辑，只调 REST/SSE |

---

## 5. 目录结构（目标形态，随阶段逐步落地）

```
project_root/
├── app/
│   ├── __init__.py
│   ├── main.py                    # FastAPI 入口：注册路由、全局异常、日志中间件
│   ├── config/
│   │   ├── __init__.py
│   │   └── settings.py            # pydantic-settings 读取 .env，集中配置
│   ├── routers/
│   │   ├── __init__.py
│   │   ├── document.py            # 文件上传/解析接口
│   │   ├── knowledge_base.py      # 知识库管理接口
│   │   └── chat.py                # RAG 问答 SSE 接口
│   ├── service/
│   │   ├── __init__.py
│   │   ├── document_service.py    # 文档上传/解析/清洗编排
│   │   ├── parser/
│   │   │   ├── __init__.py
│   │   │   ├── base.py            # DocumentParser 抽象接口（可扩展 OCR 等）
│   │   │   ├── txt_parser.py      # txt 解析
│   │   │   ├── pdf_parser.py      # pdfplumber 解析，基线与降级
│   │   │   ├── block.py            # 结构化文档块模型（标题/段落/表格等）
│   │   │   └── mineru_parser.py    # 本地 MinerU 解析适配器
│   │   ├── embedding_service.py   # Embedding 抽象
│   │   ├── chunk_service.py       # 分块：chunk_size + overlap
│   │   ├── vector_service.py      # Milvus 操作封装
│   │   ├── vector_rebuild_service.py # 对账+补偿重建工具
│   │   ├── knowledge_base_service.py # 知识库增删查
│   │   ├── llm_service.py         # LLM 流式调用封装
│   │   └── rag_service.py         # 问答编排：召回+拼prompt+SSE
│   ├── models/
│   │   ├── __init__.py
│   │   ├── schemas.py             # Pydantic 请求/响应模型
│   │   └── orm/                   # SQLAlchemy 表结构
│   │       ├── __init__.py
│   │       ├── knowledge_base.py
│   │       ├── document.py
│   │       └── chunk.py
│   ├── static/                     # 前端单页（托管在 / 根路径）
│   │   └── index.html             # 三个 Tab：知识库管理 / 文档上传 / RAG 问答
│   └── utils/
│       ├── __init__.py
│       ├── clean_text.py          # 文本清洗（可配置开关）
│       ├── exceptions.py          # 业务异常 / 系统异常定义
│       ├── response.py             # 统一返回体 {code, msg, data}
│       ├── logger.py              # 全局日志（记录入参/文件名/异常堆栈）
│       └── file_utils.py          # 文件校验、uuid 重命名、保存
├── deploy/
│   ├── docker-compose.yml         # 全栈一键启动（MySQL/Milvus/MinerU/Ollama/后端，挂载宿主本地模型）
│   ├── docker-compose.milvus.yml  # Milvus 单机部署（etcd+MinIO+standalone）
│   └── docker-compose.mineru.yml  # MinerU 4.0 本地 V1 API 服务（宿主 8001，GPU）
├── sql/                           # MySQL 建表 SQL（权威版本）
│   └── schema.sql                 # 三张表完整 DDL
├── scripts/                       # 工具脚本
│   ├── verify_schema.py           # ORM ↔ DB 字段一致性校验
│   └── rebuild_vectors.py         # 向量重建（对账+补偿）
├── tests/                         # 回归测试（解析基线等）
├── uploads/                       # 上传文件存储目录
├── logs/                          # 日志目录
├── docs/                          # 文档目录
│   ├── PROJECT_PLAN.md            # 本计划文档（唯一事实来源）
│   └── TECH_DESIGN.md             # 技术设计与面试要点
├── AGENTS.md                      # 协作约定（供不同 AI Agent 遵守）
├── requirements.txt
├── requirements-dev.txt           # 测试工具依赖（fpdf2 等）
├── .env.example                   # 环境变量模板；.env 为本地真实配置
├── .gitignore
└── README.md
```

---

## 6. 技术设计方案（详见 TECH_DESIGN.md）

各模块的**技术方案、设计理由与面试讲解要点**统一沉淀在 [`TECH_DESIGN.md`](TECH_DESIGN.md)

---

## 7. 开发规则（硬性约束）

1. 严格按照模块分阶段开发，**禁止一次性生成全部完整项目代码**；一个模块完成经确认后，再开发下一阶段；每写完一块代码附带核心逻辑讲解。
2. 偏工业后端思路：必须考虑边界情况、异常捕获、参数校验，拒绝玩具 demo 代码。
3. 代码注释完整，关键函数增加 docstring，每段代码附原理讲解（逐行看懂，用于面试讲解）。
4. 每个阶段完成后输出：**目录结构、接口文档、curl 测试命令、本模块设计思路、下一阶段改造扩展点**。
5. 所有接口参数全部使用 Pydantic 强校验。
6. 日志打印关键信息：接口入参、文件名称、异常堆栈。
7. **版本管理约定**：**小步提交**——改动不要攒，做完一小块立即提交到 `dev` 分支（本地）；`dev → main` 的合并与推送远程由用户执行。
8. **下载 / 网络约定**：任何下载动作前，先明确说明**是否需要代理**，再执行。规则如下：
   - **需要代理**：GitHub（git push/pull、release）、docker.io 官方仓库、官方 PyPI、HuggingFace 本体；
   - **不需要代理（直连更快，开着代理反而可能拖慢或干扰）**：DaoCloud 镜像站、清华 PyPI（`pypi.tuna.tsinghua.edu.cn`）、阿里 `mirrors.aliyun.com`（**实测本机极慢 ~90kB/s 且频繁断流，不推荐**）、ModelScope、`hf-mirror.com`；
   - Docker/Dockerfile 内的下载**不走宿主机代理设置**，需单独在 Docker Desktop 配置；构建里的 pip 统一用清华源并加 `--mount=type=cache` 缓存挂载；
   - 大文件/模型下载优先由用户执行，用户处理不了时由 AI 接管。
   - 判断下载成功看实际产物（如 `docker images`），**不要看 PowerShell 的退出码**——Docker 进度写 stderr 会被误判为失败。
9. **文档同步约定（强制，所有协作 Agent 共同遵守）**：任何改动都必须同步更新对应文档，**禁止"改代码不更文档"**。映射关系：
   - **任何改动** → `docs/PROJECT_PLAN.md`：更新头部版本号与「最近更新」日期、修改对应章节、在「变更记录」追加一行；
   - **设计决策 / 方案取舍 / 原理讲解** → `docs/TECH_DESIGN.md`；
   - **表结构变更** → 同步 `sql/schema.sql`，并跑 `python scripts/verify_schema.py` 校验 ORM ↔ 实际库字段一致；
   - **配置项增删改** → `.env` 与 `.env.example` 同步（模板不含真实密钥）；
   - **README 必检项（每次改动都要过一遍）**：当前进度、启动步骤、已提供接口表、目录结构、依赖与环境要求、解析器/服务开关说明——凡涉及就更新 `README.md`；
   - **部署方式变更** → `deploy/` 下对应说明文件；
   - 接手本项目前先读 `docs/PROJECT_PLAN.md`；一次改动涉及多处文档时**一并更新**，不要只改代码。

---

## 8. 阶段计划与进度跟踪

### 8.0 阶段总览

**执行顺序**（2026-09-18 调整）：`8 收尾 → 9 → 6 → 10 → 7`。
第十一阶段对照实验**延期**，不纳入本轮执行；第六、七阶段后移，分别在异步任务机制和本地 LLM 定型后收口。

| 阶段 | 内容 | 执行顺序 | 状态 |
|---|---|---|---|
| 第一阶段 | 项目骨架 + 文件上传解析模块 | ① | ✅ 已完成 |
| 第二阶段 | 文本分块 + MySQL 元数据存储 | ② | ✅ 已完成 |
| 第三阶段 | Embedding 接入 + Milvus 向量入库 | ③ | ✅ 已完成 |
| 第四阶段 | 知识库管理接口（含级联删除） | ④ | ✅ 已完成 |
| 第五阶段 | RAG 问答接口（召回 + SSE 流式 + 溯源）+ 前端单页 | ⑤ | ✅ 已完成 |
| 第八阶段 | 本地 MinerU 部署与结构化解析 | ⑥ | ✅ 已完成（`assets` 移交第九阶段） |
| 第九阶段 | 结构化分块、异步入库与解析降级 | ⑦ | ✅ 已完成 |
| 第六阶段 | 工程稳定性优化 | ⑧ | ✅ 已完成 |
| 第十阶段 | Ollama 本地 LLM 与全链路私有化 | ⑨ | ✅ 已完成 |
| 第七阶段 | 容器部署（Dockerfile + docker-compose） | ⑩ | ✅ 已完成 |
| 第十一阶段 | pdfplumber / MinerU 对照实验与面试报告 | 延期 | ⏸ 延期，不纳入本轮 |

> 状态标记：⬜ 未开始 ｜ 🟡 进行中 ｜ ✅ 已完成

### 8.0.1 接续指引（新会话/新 Agent 从这里开始）

- **当前进度**：第一~十阶段（不含第十一阶段）已完成；第十一阶段延期；
- **环境**：Python 用 conda 环境 `rag_kb`；MySQL 本机常驻；Milvus `docker compose -f deploy/docker-compose.milvus.yml up -d`；MinerU `docker compose -f deploy/docker-compose.mineru.yml up -d`（`127.0.0.1:8001`，**容器启动后首次解析需等 vLLM warmup 约 2~3 分钟**）；后端 `uvicorn app.main:app --reload`（8000）；
- **代码地图**：解析器 `app/service/parser/`（新增格式改 `__init__.py` 注册表）；分块 `chunk_service.py`；入库与降级 `document_service.py`；检索问答 `rag_service.py`；向量库 `vector_service.py`；配置 `app/config/settings.py` + `.env`；表结构 `sql/schema.sql`（改表后跑 `scripts/verify_schema.py`）；
- **必读约定**：`AGENTS.md`——小步提交（只提交 `dev`）、改完必回写文档、下载前说明是否需要代理；
- **已知技术债**：Milvus 本地持久化仍有丢失风险（已有 `scripts/rebuild_vectors.py` 兜底）；第十一阶段对照实验尚未执行。

### 8.1 第一阶段：项目骨架 + 文件上传解析（✅ 2026-08-20）

- 目录骨架 / `main.py` 入口 / `settings.py` + `.env`；统一返回体 `{code, msg, data}` + 全局异常捕获 + 全局滚动日志；
- 上传接口（后缀白名单、流式 ≤20MB 大小校验、uuid 命名、失败自动清理落盘）；
- 解析：`DocumentParser` 抽象 + txt（UTF-8/GBK 自适应）+ pdfplumber PDF，扫描版检测，可配置文本清洗；返回预览片段 + 总字符数。

### 8.2 第二阶段：文本分块 + MySQL 元数据（✅ 2026-08-21）

- 分块：`chunk_size` + `overlap` 滑动窗口按页切分（默认 500/50，分块原理见 TECH_DESIGN §5）；
- MySQL 三表 `knowledge_bases` / `documents` / `chunks`，ORM 启动自动建库（建表 DDL 见 `sql/schema.sql`）；
- 上传全链路单事务落库（元数据 + 分块），响应新增 `chunk_count`；连接池 `pre_ping/recycle/max_overflow`。

### 8.3 第三阶段：Embedding + Milvus 向量入库（✅ 2026-08-27）

- **bge-m3**（1024 维）本地权重加载，GPU（cuda）推理（懒加载 + 单例）；
- Milvus collection + `vector_service`（主键 = chunk id，COSINE + HNSW）；
- 入库双写 MySQL + Milvus 并补偿删除（先 MySQL 落库拿 id → 再写 Milvus → 回填 vector_id）；Milvus docker-compose 部署。

### 8.4 第四阶段：知识库管理接口（✅ 2026-08-28）

- 知识库增删查（name 唯一）+ 文档删除级联（Milvus 向量 → MySQL chunks → documents → 磁盘）+ 上传挂 `kb_id`；
- 级联顺序要点：先删 Milvus、再子表、后父表——批量 `Query.delete()` 不触发 ORM 关系级联，须显式排序（详见 TECH_DESIGN §10）；
- 前端：知识库管理页每行可打开「文档列表」弹窗，支持单文档删除（v1.8 补齐）。

### 8.5 第五阶段：RAG 问答接口 + 前端单页（✅ 2026-09-01）

- 问答链路：问题向量化 → Milvus 召回 top-k → 相似度阈值过滤 → MySQL 溯源 → 拼上下文 → SSE 流式（`start`/`delta`/`done`）；DeepSeek 官方 API（httpx 手动解析 SSE）；防幻觉双保险 + 流式容错；
- 配前端单页：知识库管理 / 文档上传 / RAG 问答三个 Tab（fetch + ReadableStream 消费 SSE，FastAPI 同源托管）；
- 对账 + 补偿（v1.6）：查询兜底判定"向量丢失"自动后台重建（`vector_rebuild_service`），用于修复"MySQL 有记录但 Milvus 没向量"；
- 上传去重与显式覆盖：同一知识库下同名文件默认拒绝；`overwrite=true` 时先完成新文档处理，成功后再清理旧文档，避免处理中断造成数据丢失。

### 8.6 第六阶段：工程稳定性优化（✅ 2026-09-18，执行顺序 ⑧）

> 本阶段在第九阶段异步任务机制完成后收口；任务重试、超时、幂等由异步 worker 统一实现。

- 输入字符数与轻量 token 估算双重保护；
- 大模型首 token 前超时/网络重试与指数退避；
- 进程内滑动窗口接口限流；
- `trace_id`、RAG 分阶段耗时、输入/输出 token 统计日志；
- MinerU 首次连接失败的客户端瞬时重试。

### 8.7 第七阶段：容器部署（✅ 2026-09-18，执行顺序 ⑩）

- `Dockerfile` 使用 DaoCloud Python 基础镜像、清华 PyPI 和 BuildKit pip 缓存；
- `deploy/docker-compose.yml` 统一编排后端、MySQL、Milvus、MinerU、Ollama，并保留健康检查、持久卷和本机端口覆盖；
- **模型全部挂载宿主本地权重，离线可用**：Ollama 模型仓库默认 `<工作区>/models`（含 `qwen3:8b`）挂到 `/root/.ollama/models`，bge-m3 默认 `<工作区>/bge-m3` 只读挂到 `/models/bge-m3`；不再需要 `ollama pull`，也不从 HuggingFace 下载；
- 相对路径以 compose 文件所在目录为基准（`../../models`、`../../bge-m3`），可用 `OLLAMA_MODELS_HOST_PATH` / `EMBEDDING_MODEL_HOST_PATH` 覆盖；
- Ollama 健康检查为 `ollama show qwen3:8b`（模型真能列出才算就绪，顺带验证模型目录挂载），后端 `depends_on` 该健康状态；
- `deploy/README.md` 补充模型准备、构建/启动/验证命令、端口冲突与显存竞争说明。

### 8.8 第八阶段：本地 MinerU 部署与结构化解析（✅ 2026-09-18）

> 六条要求中五条完成；`assets`（图片/表格素材）**移交第九阶段**（结构化分块时才会用到），因此本阶段标记完成。

- 使用 Docker/WSL2 部署本地 MinerU，运行时不调用 MinerU 公有云 API，企业 PDF 不离开客户环境；
- 保留 `uploads/` 作为原始文件仓库、解析重试、故障降级和实验复现数据源；
- 扩展 `ParseResult`，在兼容 `text`/`page_texts` 的基础上增加结构化 `blocks`、`assets`、解析器名称与版本；
- 新增 `DocumentBlock` 模型和 `MinerUParser` 本地解析适配器；
- `pdfplumber` 保留为基线解析器和 MinerU 不可用时的降级方案；
- 通过 `.env` 配置解析器，不在业务代码中写死具体实现。

当前进度（2026-09-18）：
- ✅ 解析结果模型（`DocumentBlock` + `ParseResult` 结构化字段）、解析器选择配置、MinerU 4.0 V1 API 适配器、本地部署说明均已完成；
- ✅ 官方 GPU 镜像 `mineru:4` 已构建完成（MinerU 4.0.1，含标准档模型权重，39.9GB）；
- ✅ 新增项目自用 compose `deploy/docker-compose.mineru.yml`（宿主 **8001** → 容器 8000，只绑回环，避开本项目 8000 端口）；
- ✅ **多格式支持**：`.txt/.md` 走原生轻量解析；`.pdf` 由 `PDF_PARSER` 决定；`.doc/.docx/.ppt/.pptx/.xls/.xlsx` 与 `.png/.jpg/.jpeg` 交给本地 MinerU；
- ✅ **PDF 降级保护**：`PDF_PARSER=mineru` 时 MinerU 失败自动回退 pdfplumber，并在 `documents.parse_error` 记录降级原因 + 响应透出 `parser_name`/`degraded`；
- ✅ MIME 按扩展名推断（不再写死 `application/pdf`）；`page_texts` 为空时按整篇单页兜底（避免分块 0 块）；
- ✅ 真实验收：txt / md / pdf / docx / png **五种格式全部上传解析成功**（图片走 OCR）；停掉 MinerU 后 PDF 上传自动降级 pdfplumber 且不失败；
- ✅ 第九阶段已收口：异步 worker、独立 `degraded` 状态、assets manifest、SHA-256/解析缓存均已接入；
- ✅ MinerU 首次冷启动仍可能较慢，但客户端已对首次连接拒绝/连接超时做指数退避重试，避免瞬时不可用直接失败。

### 8.9 第九阶段：结构化分块、异步入库与解析降级（✅ 已完成，执行顺序 ⑦）

> 本阶段已完成，让第八阶段拿到的结构化块真正参与分块和溯源。
> 从第八阶段移交进来的事项：`assets`（图片/表格素材）填充、`degraded` 由 `parse_error` 文本升级为独立状态。

- **结构化分块**：分块优先消费 MinerU 的标题、段落、表格、列表等结构块；表格保留为完整语义块，超长块再滑动窗口切分；无结构块（如 txt / pdfplumber）时回退现有按页分块逻辑；
- **chunk 溯源元数据扩展**：每个 chunk 保留来源页码、块类型、标题路径 → 需给 `chunks` 表新增字段（`block_type`、`heading_path` 等），同步 `sql/schema.sql` 与 ORM，并跑 `scripts/verify_schema.py`；
- **异步入库**：上传流程改为 `pending → processing → completed / degraded / failed`，避免 MinerU 阻塞同步上传请求（MinerU 单篇约 3 秒，首次 warmup 可达 2~3 分钟）；
- **独立 worker**：扫描数据库任务表，保存 MinerU 任务状态，支持超时、重试、幂等和服务重启恢复；
- **降级状态**：MinerU 失败但 pdfplumber 成功时标记 `degraded`（回退逻辑第八阶段已实现，本阶段把它升级为独立状态值，不再只写 `parse_error` 文本）；
- **去重与缓存**：文件 SHA-256 + 解析结果缓存，避免重复解析和重复消耗本地 GPU；
- **`assets` 填充**：解析结果中的图片/表格素材入库或落盘，供结构化分块与前端展示使用。

### 8.10 第十阶段：Ollama 本地 LLM 与全链路私有化（✅ 2026-09-18，执行顺序 ⑨）

- `LLM_PROVIDER=deepseek/ollama` 配置切换，保留统一 `stream_chat()` 调用面；
- Ollama 使用原生 `/api/chat` 流式协议并显式 `think=false`，已实测 `qwen3:8b` 返回正文；
- Embedding 继续使用本地 `bge-m3`，形成本地 MinerU + 本地 Embedding + Milvus + MySQL + Ollama 链路；
- 不提前实现 SaaS/公有云、多租户、客户专属云、托管私有云、混合云或一体机交付形态。

### 8.11 第十一阶段：对照实验与面试报告（⏸ 延期）

> 本轮按用户要求延期，不执行对照实验和报告产出；保留下面的实验设计，后续单独安排。

- 固定同一批普通文本、双栏、扫描件、复杂表格、公式和多级标题 PDF；
- 对比 `pdfplumber + 原有分块` 与 `MinerU + 结构化分块`；固定 Embedding、Top-K、提示词和问题集；
- 记录文本完整率、表格结构正确率、OCR 效果、Recall@K、MRR、问答准确率、页码引用准确率、解析耗时、资源占用、失败率和降级率；
- 不预设 MinerU 必然更好，以真实数据决定默认解析器，并形成可用于面试说明技术选型的实验报告。

---

## 9. 每阶段交付物模板（输出固定格式）

1. **目录结构**：本阶段落地后的目录树
2. **接口文档**：方法、路径、请求/响应示例（含错误码表）
3. **curl 测试命令**：可直接复制的验证命令
4. **设计思路**：模块职责、关键流程、边界处理、原理讲解
5. **下阶段改造扩展点**：本阶段预留了什么、下阶段怎么接

---

## 10. 变更记录

| 日期         | 版本 | 变更内容 | 原因 |
|------------|---|---|---|
| 2026-08-20 | v0.1 | 初版：基于原始方案 + 评审修正 | PDF 解析改用 pdfplumber；新增 embedding 抽象、双写一致性、SSE 协议、Milvus 引入时机等设计决策；建立进度跟踪机制 |
| 2026-08-20 | v0.2 | 骨架落地调整：`.env.example` 统一放项目根目录（原文档标在 `config/` 下）；`requirements.txt` 提前至骨架阶段 | 遵循 Python 项目惯例（`.env` 在根目录加载）；依赖文件是安装骨架的前提 |
| 2026-08-20 | v0.3 | 任务 2+3 合并开发（统一返回体 + 全局异常 + 全局日志，二者耦合无法拆分）；`/health` 也套统一信封 | 任务 2 要求"异常打印完整堆栈日志"，必须先有全局日志设施；接口格式一致性 |
| 2026-08-20 | v0.4 | 任务 4 上传接口完成：新增 `utils/file_utils.py`、`models/schemas.py`（泛型信封 `ApiResponse[T]`）、`service/document_service.py`、`routers/document.py` | 上传校验 + 落盘 + 响应契约；解析与 preview/char_count 留待任务 5/6 填充 |
| 2026-08-20 | v0.5 | 任务 5+6 完成，第一阶段收官：DocumentParser 抽象 + txt/pdf 解析器 + 扫描版检测 + clean_text 可配置清洗 + 上传全链路（preview/char_count 填充）；解析失败自动清理落盘文件；新增 `requirements-dev.txt`（fpdf2 测试工具） | 完成第一阶段全部任务；修复"解析失败残留文件"问题；清洗/预览配置入 .env |
| 2026-08-20 | v0.6 | 新增版本管理约定（开发规则第 7 条）：阶段完成推 dev → 确认后合 main 再推远程；远程 dev 分支已创建 | 用户指定分支工作流 |
| 2026-08-21 | v0.7 | 第二阶段完成：chunk_service（滑动窗口 + 按页分块 + 边界校验）+ MySQL ORM 三表 + 上传全链路落库（单事务）+ 响应新增 chunk_count；修复建库 URL 与引擎缺库名两个 bug | 完成第二阶段；真实 MySQL 全链路验证通过 |
| 2026-08-21 | v0.8 | 新增 `TECH_DESIGN.md`：技术方案与面试要点文档（分层/上传/解析/清洗/分块原理/MySQL 表设计/连接池/事务/双写一致性/面试 Q&A/踩坑记录） | 沉淀技术方案供面试复习 |
| 2026-08-21 | v0.9 | 工作流调整：合 main + 推远程由用户自行执行（AI 只推 dev）；`TECH_DESIGN.md` 移除运维/环境层面琐碎问题记录 | 用户指定；文档只保留有讲解价值的代码设计与面试要点 |
| 2026-08-27 | v1.0 | 第三阶段完成：bge-m3（GPU）+ Milvus docker-compose 部署 + Embedding 抽象 + vector_service + 入库全链路（双写一致 + 补偿）；修复 pymilvus 3.0 API 兼容、load_collection 缺失、补偿删除孤儿 chunk 三个真实问题；文档头部增加版本/更新时间，目录结构同步 | 完成第三阶段；真实 Milvus + GPU 全链路验证通过 |
| 2026-08-27 | v0.10 | 第三阶段完成：bge-m3（1024 维）+ Milvus 向量入库全链路；环境切 conda `rag_kb`（GPU torch）并本地加载 bge-m3 权重 | 国内下载 GPU torch / bge-m3 权重过慢，改为手动下载 + 本地路径加载 |
| 2026-08-28 | v1.1 | 第四阶段完成：知识库增删查 + 文档删除级联（Milvus/MySQL/文件三层清理）+ 上传挂知识库；新增 knowledge_base_service/router | 完成第四阶段；级联删除顺序、name 唯一、错误场景全部实测通过 |
| 2026-08-28 | v1.2 | 字段一致性对齐：以实际数据库为准补齐 ORM（knowledge_bases 补 owner_id/embedding_model/chunk_strategy/chunk_size/chunk_overlap/doc_count/status/updated_at；documents 补 file_type/status/parse_error/updated_at；chunks 补 token_count/embedding_status）；代码接入这些字段（file_type/status=2/embedding_status=1/doc_count 上传自增删除自减）；PROJECT_PLAN DDL 更新为权威版本；新增 scripts/verify_schema.py 校验工具 | 修复 ORM/文档/实际库三方字段不一致 |
| 2026-08-28 | v1.3 | README 补全（第四阶段进度、接口清单、前端说明、环境注意）；新增第 11 节「前端页面设计」（单页 HTML，三个 Tab：知识库管理/文档上传/RAG 问答） | 完善项目文档与前端规划，待第五阶段后开发 |
| 2026-09-01 | v1.4 | 第五阶段完成：RAG 问答接口（问题向量化→召回→阈值过滤→溯源→拼上下文→SSE 流式生成）；DeepSeek 官方 API（deepseek-v4-flash，httpx 手动解析 SSE）；SSE 协议 start/delta/done；防幻觉双保险（min_similarity + 系统提示词） | 完成第五阶段；真实验证相关问题/无关问题均正确 |
| 2026-09-01 | v1.5 | 前端单页实现：`app/static/index.html` 三个 Tab（知识库管理/文档上传/RAG 问答），fetch+ReadableStream 消费 SSE；FastAPI 同源托管（挂载需在所有路由之后，修复遮蔽 /health 问题） | 配套前端落地，便于可视化测试 |
| 2026-09-01 | v1.6 | 对账+补偿机制落地（6.5）：① 重建逻辑抽为 `vector_rebuild_service.py` 可调度函数（CLI/定时器/查询兜底复用）；② 查询兜底分级——召回空但有文档→自动后台重建+明确提示，真没文档→提示上传，正常无关→答未找到；修复 `ensure_collection` 进程内缓存导致集合丢失后不重建的 bug | 解决"MySQL 有记录但 Milvus 没向量"的一致性与用户体验问题 |
| 2026-09-09 | v1.7 | 文档结构调整：前端内容并入第五阶段；「核心设计决策」精简为指向 TECH_DESIGN.md 的指引（避免重复维护）；三表 DDL 抽离至 `sql/schema.sql`；技术栈/分层架构/目录结构同步（补前端、DeepSeek API、static/scripts/sql）；各阶段明细压缩为结果概览 | 前端已实现，文档与 TECH_DESIGN 去重、SQL 独立成文件、计划文档简化 |
| 2026-09-09 | v1.8 | 上传去重：同一知识库下 `original_filename` 同名拒绝，避免重复文件造成检索结果成对重复；前端补齐：知识库管理每行新增「文档」按钮，弹窗展示文档列表（文件名/大小/分块数/上传时间）+ 单文档删除按钮（调 DELETE /documents/{file_id}） | 修复「来源重复」问题；补齐文档管理最小闭环 |
| 2026-09-17 | v1.9 | 明确项目当前定位为客户本地部署；规划本地 MinerU、结构化解析/分块、异步入库、解析降级、Ollama 全链路私有化及对照实验报告；保留 pdfplumber 作为基线与降级方案，并记录后续可扩展的其他交付模式 | 兼顾当前学习项目的逐步演进与企业文档私有化目标，避免提前引入 SaaS/多租户等无关复杂度 |
| 2026-09-17 | v1.10 | 第六阶段前置与第八阶段启动：新增解析回归测试、pdfplumber/TXT 解析耗时与结果日志；`ParseResult` 扩展结构化 blocks/assets/解析器元数据；新增 MinerU 4.0 本地 V1 API 适配器、配置项和部署说明 | 建立现有解析基线，并开始接入官方 MinerU 4.0 本地服务；镜像构建与真实 PDF 验收待继续完成 |
| 2026-09-17 | v1.11 | 新增下载/网络约定（开发规则第 8 条）：下载前先说明是否需要代理，列出需代理/直连的源清单；`mineru:4` 本地镜像构建完成（39.9GB，MinerU 4.0.1 + 标准档模型权重；Dockerfile 改：pip 换清华源+阿里兜底、去掉 `-U` 无谓重装 torch、加 pip 缓存挂载、删除会触发 docker.io 的 `# syntax` 行） | 网络下载是本项目最高频阻塞点（aliyun 源 90kB/s 反复断流导致多次构建失败）；镜像构建打通，第八阶段可继续真实 PDF 验收 |
| 2026-09-18 | v1.12 | 新增开发规则第 9 条「文档同步约定（强制）」+ 项目根 `AGENTS.md`（协作约定，供不同 AI Agent 遵守）；新增 `deploy/docker-compose.mineru.yml`（MinU V1 API 服务，宿主 8001→容器 8000，GPU 预留，只绑回环）；配置清理：删除死配置 `HOST`/`PORT`（uvicorn 命令行决定）与无用 `MINERU_API_KEY`（本地服务无鉴权），`.env` 补上 MinerU 配置块；第八阶段真实 PDF 验收通过（2 页 / 6 块 / 类型识别正确含 table / 3.09s） | 让协作者与不同 Agent 都遵守"改动必须回写文档"；打通 MinerU 本地解析并清理配置噪音 |
| 2026-09-18 | v1.13 | README 全量对齐：修正文档路径（根目录 → `docs/`）、补第八阶段进度、补目录结构/接口/环境说明、新增「文档解析器（pdfplumber/MinerU）」章节；规则第 9 条补充 **README 必检项**（进度/启动/接口表/目录/依赖环境/开关说明） | README 是外部读者第一入口，必须与代码和计划保持同步 |
| 2026-09-18 | v1.14 | 协作约定调整：规则第 7 条改为**小步提交**（改动不攒、做完一小块立即提交 dev）；`AGENTS.md` 精简重写（去除冗余说明，保留提交/文档矩阵、下载网络、环境、开发四节） | 降低协作约定的阅读成本，提高执行率 |
| 2026-09-18 | v1.15 | 第八阶段收尾：**多格式支持**（txt/md 原生；pdf 由 `PDF_PARSER` 决定；doc/docx/ppt/pptx/xls/xlsx/png/jpg/jpeg 交 MinerU）；**PDF 降级保护**（`FallbackDocumentParser`，MinerU 失败回退 pdfplumber + 记 `parse_error` + 响应透出 `parser_name`/`degraded`）；MIME 按扩展名推断；`page_texts` 空时整篇兜底；前端展示解析器与降级；五种格式真机验收通过（含图片 OCR） | 让"常见文档都能入库"可用，并消除 MinerU 单点故障导致上传失败的风险 |
| 2026-09-18 | v1.16 | **调整阶段执行顺序为 `8 → 9 → 6 → 10 → 11 → 7`**：第六/七阶段后移（稳定性中的超时重试幂等会被第九阶段异步任务机制吸收，避免返工；容器部署等功能定型再一次性做）；第八阶段标记完成（`assets` 移交第九阶段）；新增 **8.0.1 接续指引**（当前进度、环境命令、代码地图、必读约定、已知技术债） | 让下一阶段目标明确、新会话/新 Agent 能直接接上，避免重复劳动 |
| 2026-09-18 | v1.17 | 前端上传表单提示与后端白名单对齐：文件类型提示改为「txt/md/pdf/docx/xls/图片等」，`accept` 扩展为全部允许格式，并注明白名单由后端 `ALLOWED_EXTENSIONS` 控制；上传中 loading 文案改为「MinerU 首次解析需等引擎预热，最长约 2~3 分钟」 | 多格式支持上线后前端提示仍停留在「txt/PDF」，与实际能力不一致 |
| 2026-09-18 | v1.18 | 文档同步：README 接口表上传行由「txt/pdf ≤20MB」对齐为「txt/md/pdf/docx/xls/图片等，单文件 ≤20MB」（与前端/`.env` 白名单一致）；`requirements.txt` 补上缺失的 `httpx` 依赖（`llm_service`/`mineru_parser` 已在用）；多格式解析不新增 Python 库（doc/图片全委托外部 MinerU），`requirements-dev.txt` 无需变化 | 修复「已会用 httpx 却未声明」的依赖缺失；README 接口表与多格式支持、前端提示对齐 |
| 2026-09-18 | v1.19 | `app/main.py` 消除 lifespan 装饰器的弃用删除线：BasedPyright 内置 typeshed 中 `@asynccontextmanager` 有两个重载，返回类型标注为 `AsyncIterator[None]` 时命中带 `@deprecated` 的重载（提示改用 `AsyncGenerator`）；故把 lifespan 返回类型改为 `collections.abc.AsyncGenerator[None]`，装饰器本身并未弃用、保持不变 | 删除线来自存根的弃用重载而非装饰器本身（首轮误判为 `typing.AsyncIterator` 弃用，改为 `collections.abc.AsyncIterator` 后仍命中弃用重载，二次修正为 `AsyncGenerator` 才解决） |
| 2026-09-18 | v1.20 | 前端上传 loading 文案简化为「上传解析中…」（撤销 v1.17 加入的「MinerU 首次解析需等引擎预热，最长约 2~3 分钟」长提示） | 引擎冷启动属内部实现细节，不该暴露给使用页面；且曾评估过"后端启动时后台预热引擎"方案（实测引擎为首次解析惰性加载、约 100s），结论是**不做**——收益不抵复杂度，冷启动现状继续记录在 8.8 与 TECH_DESIGN 13.5 |
| 2026-09-18 | v1.21 | 同名文件冲突策略决策（**仅记录，暂不实施**）：`_check_duplicate` 的「一律拒绝」改为「显式覆盖」——接口新增 `overwrite: bool = False`，为 `False` 保持拒绝（安全默认），为 `True` 时**先写新文档、向量化成功后再 `purge_document` 删旧**；完整四种策略对比与实现约束见 TECH_DESIGN §2.4，排期在第九阶段之后 | 原拒绝策略的论证不完整（"避免重复向量"只能推出"不能放任重复"，推不出"必须拒绝"），企业场景改版重传被强迫先删后传；替换顺序必须限定为"先写后删"——若写成"先删旧再解析新"，解析期间新旧两侧都查不到、失败时旧数据永久丢失（`(kb_id, original_filename)` 无 DB 唯一约束，先写后删可行） |
| 2026-09-18 | v1.22 | 第九阶段启动：`chunks` 新增 `block_type` / `heading_path` 结构化溯源字段；文档状态补充 `4-降级完成`，同步更新 ORM、权威 DDL 与技术设计，保持字段可空兼容旧解析结果 | 先固化异步管线与结构化分块所需的数据契约，再逐步接入业务流程 |
| 2026-09-18 | v1.23 | 第九阶段结构化分块接入：MinerU 结构块优先按块切分，表格/短块保持完整，超长块才滑窗；无结构结果回退按页分块；入库写入 `block_type` / `heading_path`，降级文档使用独立 status=4 | 让第八阶段产出的结构化解析结果真正影响分块与溯源，同时保持 txt/pdfplumber 兼容 |
| 2026-09-18 | v1.24 | 第九阶段异步基础设施启动：新增 `document_tasks` 任务表与 ORM，记录 pending/processing/succeeded/failed、重试次数、下次执行时间、锁定时间和最近错误；同步完成 DDL、实际 MySQL 表和 schema 校验脚本 | 为后续 worker 领取任务、超时回收、重试和服务重启恢复提供持久化队列 |
| 2026-09-18 | v1.25 | 实现 worker 任务状态机 service：事务行锁领取、并发 `SKIP LOCKED`、processing 超时回收、失败退避重试、达到次数上限转终态失败并同步文档状态；真实 MySQL 完成两次领取与重试验收 | 持久任务需要在并发、进程崩溃和依赖瞬时失败时保持可恢复与不重复消费 |
| 2026-09-18 | v1.26 | 第九阶段收口：上传改为 pending 异步入队；应用生命周期启动 worker；新增文档状态接口与前端轮询；加入 SHA-256、解析结果缓存、assets manifest 落盘；任务失败补偿 Milvus；补齐 worker/缓存配置并完成真实 MySQL schema 校验 | 长耗时解析不再阻塞 HTTP 请求，重启/重试可恢复，重复文件不重复消耗 MinerU，阶段目标形成闭环 |
| 2026-09-18 | v1.27 | 异步 worker 增加重试前 Milvus 清理，确保部分向量写入后的重试幂等；补充技术设计说明 | 防止任务在向量写入中断后重试造成重复召回 |
| 2026-09-18 | v1.29 | 第六阶段启动：增加请求 `X-Trace-Id`、LLM 首 token 前重试与指数退避、可配置问题长度保护；同步更新 `.env.example` 与阶段状态 | 先落地不改变接口协议的稳定性能力，降低外部 LLM 瞬时故障和超长输入风险 |
| 2026-09-18 | v1.30 | 第六阶段继续：增加进程内 API 滑动窗口限流；RAG 记录 embedding、召回、上下文构建阶段耗时及 query/context 字符统计 | 为单实例部署提供基础过载保护和可定位的性能观测；多实例限流后续可替换 Redis |
| 2026-09-18 | v1.33 | 第六阶段补强：加入轻量 token 估算的 query/context 输入保护，done 事件改返回估算 output token 数；完善 RAG token 与总耗时日志 | 字符数不能反映中英文混合上下文的真实长度，输入保护和统计统一使用保守估算 |
| 2026-09-18 | v1.31 | 第十阶段启动：LLMService 增加 `LLM_PROVIDER=deepseek/ollama` 配置切换和 Ollama OpenAI 兼容地址；保留 DeepSeek 默认值；本机检测到 `qwen3:8b` 模型 | 先保持统一调用协议和服务接口，再逐步完成本地模型问答与断网验收 |
| 2026-09-18 | v1.32 | Ollama 适配改用原生 `/api/chat` + `think=false`，解决 qwen3 OpenAI 兼容端点将推理内容占满输出的问题；实测 `qwen3:8b` 返回正文 OK | 本地模型协议虽兼容 OpenAI，但思考模型的禁用推理参数行为不一致，原生端点可控性更好 |
| 2026-09-18 | v1.36 | 完成本轮除第十一阶段外的全部工作：显式覆盖、token 输入保护、限流与阶段耗时日志、Ollama 原生流式、Dockerfile/统一 Compose、worker 重试参数接线、MinerU 首次连接重试和离线回归测试；第十一阶段标记延期 | 按用户指定执行范围收口，补齐网络中断前遗留项并使计划、技术设计、README 与实现一致 |
| 2026-09-18 | v1.37 | 统一 Compose 改为**离线模型挂载**：Ollama 模型仓库（`qwen3:8b`）从宿主 `<工作区>/models` 挂到 `/root/.ollama/models`、bge-m3 从 `<工作区>/bge-m3` 只读挂到 `/models/bge-m3`，删除 `ollama pull` 步骤；新增 `OLLAMA_MODELS_HOST_PATH` / `EMBEDDING_MODEL_HOST_PATH` 覆盖变量与 `OLLAMA_KEEP_ALIVE=30m`；Ollama 增加 `ollama show qwen3:8b` 健康检查、后端等待其健康、Ollama 增加 GPU 预留；`deploy/README.md` 重写前置条件与构建/启动/验证命令；README 与 `.env(.example)` 同步 | 模型已由用户下载到工作区，容器应直接用本地权重（客户内网/断网场景不可依赖 `ollama pull` 与 HuggingFace 下载）；同时修正原先默认的 bge-m3 挂载路径（`../models/bge-m3` 在真实工作区布局下不存在） |
| 2026-09-18 | v1.38 | 修复 `app/config/settings.py` 的 Python 手误：`debug: bool = false` 中的小写 `false` 在类体执行时抛 `NameError`，导致 `app.main` 导入失败、`rag-backend` 容器反复重启（`Restarting (1)`）；改为 `False`，同时使代码默认值与 `.env`（`DEBUG=false`）、第 40 行注释「生产必须 false」及 compose 的 `DEBUG: ${DEBUG:-false}` 四者一致；全仓扫描确认无其他小写布尔值（`tests/test_stability.py:31` 的 `"done":true` 属 JSON 字面量，不动） | `docker compose up -d --build backend` 重建后 `/health` 返回 200、容器 healthy、7 个服务全部 Up；排查中同时清理了统一 Compose 上线后遗留的两个旧容器 `mineru-api` / `milvus-standalone`（释放约 216MB 并解除宿主 19530 端口潜在冲突） |
| 2026-09-18 | v1.39 | 修复异步入库「集合不存在即任务判死」：`vector_service.delete_by_doc` 改为**幂等**（collection 不存在时跳过删除并记日志，不再抛 `MilvusException code=100`），新增 `collection_exists()` 辅助函数；`process_document_task` 调整为**先 `ensure_collection()` 再 `delete_by_doc()`**（原顺序把"集合丢失"误判成任务失败）；写入前保留第二次 `ensure_collection()` 作为长耗时解析期间集合被删的保护 | 统一 Compose 上线后 Milvus 换用命名卷 `milvus_data`（空），旧 `deploy/volumes/milvus` 数据不再被使用，集合不存在成常态；此时异步任务第一步"清理重试残留"就抛异常，重试 3 次后文档终态失败、分块数 0。实测：补建集合 + 重新入队后 task 一次成功（55 分块、chunk_id 1~55 全部写入 Milvus） |

> 后续任何方案调整：在此表追加一行，并同步修改正文对应小节。
