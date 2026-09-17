# 企业知识库 RAG 后端系统 — 开发计划与进度跟踪

> 开发以本文档为准，任何方案调整都先改这里（在「变更记录」登记），每个阶段完成后更新「进度跟踪」。
>
> 当前版本：v1.17 ｜ 创建日期：2026-08-20 ｜ 最近更新：2026-09-18

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

**执行顺序**（2026-09-18 调整）：`8 收尾 → 9 → 6 → 10 → 11 → 7`。
第六、七阶段**后移**：稳定性优化中的超时/重试/幂等会被第九阶段的异步任务机制自然吸收（避免返工）；容器部署等功能定型后一次做完。

| 阶段 | 内容 | 执行顺序 | 状态 |
|---|---|---|---|
| 第一阶段 | 项目骨架 + 文件上传解析模块 | ① | ✅ 已完成 |
| 第二阶段 | 文本分块 + MySQL 元数据存储 | ② | ✅ 已完成 |
| 第三阶段 | Embedding 接入 + Milvus 向量入库 | ③ | ✅ 已完成 |
| 第四阶段 | 知识库管理接口（含级联删除） | ④ | ✅ 已完成 |
| 第五阶段 | RAG 问答接口（召回 + SSE 流式 + 溯源）+ 前端单页 | ⑤ | ✅ 已完成 |
| 第八阶段 | 本地 MinerU 部署与结构化解析 | ⑥ | ✅ 已完成（`assets` 移交第九阶段） |
| 第九阶段 | 结构化分块、异步入库与解析降级 | ⑦ | **⬜ 下一步做这个** |
| 第六阶段 | 工程稳定性优化 | ⑧ | ⬜ 未开始（后移） |
| 第十阶段 | Ollama 本地 LLM 与全链路私有化 | ⑨ | ⬜ 未开始 |
| 第十一阶段 | pdfplumber / MinerU 对照实验与面试报告 | ⑩ | ⬜ 未开始 |
| 第七阶段 | 容器部署（Dockerfile + docker-compose） | ⑪ | ⬜ 未开始（最后做） |

> 状态标记：⬜ 未开始 ｜ 🟡 进行中 ｜ ✅ 已完成

### 8.0.1 接续指引（新会话/新 Agent 从这里开始）

- **当前进度**：第一~五阶段、第八阶段已完成；**下一步做第九阶段**（见 8.9）；
- **环境**：Python 用 conda 环境 `rag_kb`；MySQL 本机常驻；Milvus `docker compose -f deploy/docker-compose.milvus.yml up -d`；MinerU `docker compose -f deploy/docker-compose.mineru.yml up -d`（`127.0.0.1:8001`，**容器启动后首次解析需等 vLLM warmup 约 2~3 分钟**）；后端 `uvicorn app.main:app --reload`（8000）；
- **代码地图**：解析器 `app/service/parser/`（新增格式改 `__init__.py` 注册表）；分块 `chunk_service.py`；入库与降级 `document_service.py`；检索问答 `rag_service.py`；向量库 `vector_service.py`；配置 `app/config/settings.py` + `.env`；表结构 `sql/schema.sql`（改表后跑 `scripts/verify_schema.py`）；
- **必读约定**：`AGENTS.md`——小步提交（只提交 `dev`）、改完必回写文档、下载前说明是否需要代理；
- **已知技术债**：同步上传阻塞请求（第九阶段改异步）、`assets` 未填充、`degraded` 暂记在 `parse_error` 文本、Milvus 本地持久化有丢失风险（有 `scripts/rebuild_vectors.py` 兜底）。

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
- 上传去重（v1.8）：同一知识库下同名文件拒绝上传，避免重复文件造成检索结果成对重复。

### 8.6 第六阶段：工程稳定性优化（⬜ 后移，执行顺序 ⑧）

> **已后移**：本阶段与第九阶段的异步任务机制合并收口——任务重试、超时、幂等由异步 worker 统一实现（先做本阶段会造成返工）。
> 下面两项成本低、收益直接，**可在第九阶段之前顺手做**：输入 token 长度校验、MinerU 首解析 warmup 的客户端瞬时连接重试。

- 输入 token 长度校验（目前只按字符数限长 2000，未按 token 校验）；
- 大模型请求超时与重试；
- 简易接口限流；
- 全链路详细日志（trace_id、各阶段耗时、token 统计）。

### 8.7 第七阶段：容器部署（⬜ 后移，执行顺序 ⑪）

> **最后执行**：等第九/十阶段功能定型后再做，避免镜像反复重建。

- Dockerfile + docker-compose，一键启动后端、MySQL、Milvus、MinerU（现有两份 compose 已可分别启动 Milvus 与 MinerU，本阶段补齐后端镜像与统一编排）。

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
- ⚠️ 仍待第九阶段：
  1. **异步入库**：上传仍是同步阻塞，长文档会占住请求；需改 `pending → processing → completed/degraded/failed` + 独立 worker；
  2. `degraded` 目前记录在 `parse_error` 文本里，第九阶段升级为独立状态值；
  3. `assets`（图片/表格素材）未填充；`parser_version` 硬编码 `4.x`；
  4. **首次解析慢**：MinerU 容器启动后首次解析需等 vLLM warmup（约 2~3 分钟），客户端应对瞬时连接错误做重试。

### 8.9 第九阶段：结构化分块、异步入库与解析降级（⬜ 下一步做这个，执行顺序 ⑦）

> **当前进行阶段。** 本阶段要让第八阶段拿到的结构化块真正产生价值（现在块已拿到但分块仍按页滑窗，表格会被拦腰切断、标题层级未利用）。
> 从第八阶段移交进来的事项：`assets`（图片/表格素材）填充、`degraded` 由 `parse_error` 文本升级为独立状态。

- **结构化分块**：分块优先消费 MinerU 的标题、段落、表格、列表等结构块；表格保留为完整语义块，超长块再滑动窗口切分；无结构块（如 txt / pdfplumber）时回退现有按页分块逻辑；
- **chunk 溯源元数据扩展**：每个 chunk 保留来源页码、块类型、标题路径 → 需给 `chunks` 表新增字段（`block_type`、`heading_path` 等），同步 `sql/schema.sql` 与 ORM，并跑 `scripts/verify_schema.py`；
- **异步入库**：上传流程改为 `pending → processing → completed / degraded / failed`，避免 MinerU 阻塞同步上传请求（MinerU 单篇约 3 秒，首次 warmup 可达 2~3 分钟）；
- **独立 worker**：扫描数据库任务表，保存 MinerU 任务状态，支持超时、重试、幂等和服务重启恢复；
- **降级状态**：MinerU 失败但 pdfplumber 成功时标记 `degraded`（回退逻辑第八阶段已实现，本阶段把它升级为独立状态值，不再只写 `parse_error` 文本）；
- **去重与缓存**：文件 SHA-256 + 解析结果缓存，避免重复解析和重复消耗本地 GPU；
- **`assets` 填充**：解析结果中的图片/表格素材入库或落盘，供结构化分块与前端展示使用。

### 8.10 第十阶段：Ollama 本地 LLM 与全链路私有化（规划）

- 当前阶段暂时使用 DeepSeek API，加快 RAG 功能验证；
- 后续通过 Ollama 部署本地 LLM，保持 `LLMService` 接口不变，通过配置切换模型供应商；
- 确认 Embedding 始终使用本地 `bge-m3` 或其他本地模型，避免只实现 PDF 本地解析但 Embedding 仍然出网；
- 最终形成“本地 MinerU + 本地 Embedding + Milvus + MySQL + Ollama”的客户本地部署方案；
- 当前不提前实现 SaaS/公有云、多租户、客户专属云、托管私有云、混合云或一体机交付形态，后续通过独立分支学习扩展。

### 8.11 第十一阶段：对照实验与面试报告（规划）

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

> 后续任何方案调整：在此表追加一行，并同步修改正文对应小节。
