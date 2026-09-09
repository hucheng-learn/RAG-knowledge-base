# 企业知识库 RAG 后端系统 — 开发计划与进度跟踪

> 开发以本文档为准，任何方案调整都先改这里（在「变更记录」登记），每个阶段完成后更新「进度跟踪」。
>
> 当前版本：v1.7 ｜ 创建日期：2026-08-20 ｜ 最近更新：2026-09-09

---

## 1. 项目概述

开发一个简历可用、偏工业级的企业知识库 RAG 后端系统，配套极简前端页面。

- **背景**：本项目用于面试讲解项目原理。
- **目标**：文档上传 → 解析 → 清洗 → 分块 → 向量化 → 入库；用户提问 → 召回 → 拼上下文 → 大模型 SSE 流式回答 + 溯源。
- **开发方式**：严格按模块分阶段开发，**禁止一次性生成全部代码**，一个模块确认后再进入下一阶段。

---

## 2. 技术栈

| 层次 | 选型 | 说明 |
|---|---|---|
| Web 框架 | Python + FastAPI | 异步、Pydantic 强校验、自带 OpenAPI 文档 |
| PDF 解析 | **pdfplumber** |
| 文本解析 | 内置 open() 读取 | txt 直接读取 |
| 向量库 | Milvus | 只存 embedding 向量，与 MySQL 元数据一一关联 |
| 元数据库 | MySQL | 知识库、文档、chunk 元数据 |
| Embedding | **bge-m3** | 本地 sentence-transformers 加载，1024 维；|
| 大模型 | DeepSeek 官方 API（OpenAI 兼容） | 对话/生成，SSE 流式输出（`deepseek-v4-flash`） |
| ORM | SQLAlchemy 2.x | 配合 MySQL |
| 前端 | 单页 HTML + 原生 JS | FastAPI 静态同源托管（`app/static/`），fetch + ReadableStream 消费 SSE，无构建工具 |
| 配置 | pydantic-settings + .env | 禁止硬编码 |
| 部署 | Docker / docker-compose | Milvus 已用 compose 部署，后端一键启动留待后续阶段 |

---

## 3. 整体业务流程

### 3.1 文档入库流程

```
文档上传 → 文件解析 → 文本清洗 → 文本分块(chunk)
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
│   │   │   └── pdf_parser.py      # pdfplumber 解析，逐页提取
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
│   └── docker-compose.milvus.yml  # Milvus 单机部署（etcd+MinIO+standalone）
├── sql/                           # MySQL 建表 SQL（权威版本）
│   └── schema.sql                 # 三张表完整 DDL
├── scripts/                       # 工具脚本
│   └── verify_schema.py          # ORM ↔ DB 字段一致性校验
├── uploads/                       # 上传文件存储目录
├── logs/                          # 日志目录
├── PROJECT_PLAN.md                # 本计划文档
├── TECH_DESIGN.md                 # 技术设计与面试要点文档
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
7. **版本管理约定**：每个阶段完成 → 提交到 `dev` 分支。

---

## 8. 阶段计划与进度跟踪

### 8.0 阶段总览

| 阶段 | 内容 | 状态 |
|---|---|---|
| 第一阶段 | 项目骨架 + 文件上传解析模块 | ✅ 已完成 |
| 第二阶段 | 文本分块 + MySQL 元数据存储 | ✅ 已完成 |
| 第三阶段 | Embedding 接入 + Milvus 向量入库 | ✅ 已完成 |
| 第四阶段 | 知识库管理接口（含级联删除） | ✅ 已完成 |
| 第五阶段 | RAG 问答接口（召回 + SSE 流式 + 溯源）+ 前端单页 | ✅ 已完成 |
| 第六阶段 | 工程稳定性优化 | ⬜ 未开始 |
| 第七阶段 | 容器部署（Dockerfile + docker-compose） | ⬜ 未开始 |

> 状态标记：⬜ 未开始 ｜ 🟡 进行中 ｜ ✅ 已完成

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
- 级联顺序要点：先删 Milvus、再子表、后父表——批量 `Query.delete()` 不触发 ORM 关系级联，须显式排序（详见 TECH_DESIGN §10）。

### 8.5 第五阶段：RAG 问答接口 + 前端单页（✅ 2026-09-01）

- 问答链路：问题向量化 → Milvus 召回 top-k → 相似度阈值过滤 → MySQL 溯源 → 拼上下文 → SSE 流式（`start`/`delta`/`done`）；DeepSeek 官方 API（httpx 手动解析 SSE）；防幻觉双保险 + 流式容错；
- 配前端单页：知识库管理 / 文档上传 / RAG 问答三个 Tab（fetch + ReadableStream 消费 SSE，FastAPI 同源托管）；
- 对账 + 补偿（v1.6）：查询兜底判定"向量丢失"自动后台重建（`vector_rebuild_service`），用于修复"MySQL 有记录但 Milvus 没向量"。

### 8.6 第六阶段：工程稳定性优化（预留）

- 输入 token 长度校验、大模型请求超时与重试、简易接口限流、全链路详细日志。

### 8.7 第七阶段：容器部署（预留）

- Dockerfile + docker-compose，一键启动后端、MySQL、Milvus 服务。

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

> 后续任何方案调整：在此表追加一行，并同步修改正文对应小节。
