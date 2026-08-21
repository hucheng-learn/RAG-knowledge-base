# 企业知识库 RAG 后端系统 — 开发计划与进度跟踪

> 本文件是项目的**唯一事实来源（source of truth）**：开发以本文档为准，任何方案调整都先改这里（在「变更记录」登记），每个阶段完成后更新「进度跟踪」。
>
> 当前版本：v0.1 ｜ 创建日期：2026-08-20

---

## 1. 项目概述

开发一个简历可用、偏工业级的企业知识库 RAG 后端系统，配套极简前端页面。

- **背景**：3 年 Java 后端经验，大模型学习 2 个月，本项目用于面试讲解项目原理。
- **目标**：文档上传 → 解析 → 清洗 → 分块 → 向量化 → 入库；用户提问 → 召回 → 拼上下文 → 大模型 SSE 流式回答 + 溯源。
- **开发方式**：严格按模块分阶段开发，**禁止一次性生成全部代码**，一个模块确认后再进入下一阶段。

---

## 2. 技术栈

| 层次 | 选型 | 说明 |
|---|---|---|
| Web 框架 | Python + FastAPI | 异步、Pydantic 强校验、自带 OpenAPI 文档 |
| PDF 解析 | **pdfplumber**（修正项，见 6.1） | 原方案 PyPDF2 已维护模式，解析质量差 |
| 文本解析 | 内置 open() 读取 | txt 直接读取 |
| 向量库 | Milvus | 只存 embedding 向量，与 MySQL 元数据一一关联 |
| 元数据库 | MySQL | 知识库、文档、chunk 元数据 |
| Embedding | **待定（独立抽象，见 6.2）** | 首选本地 bge-m3 / bge-large-zh，deepseek-harness 不提供 embedding |
| 大模型 | 本地 deepseek-harness 服务 | 对话/生成，SSE 流式输出 |
| ORM | SQLAlchemy 2.x | 配合 MySQL |
| 配置 | pydantic-settings + .env | 禁止硬编码 |
| 部署 | Docker / docker-compose | 后续阶段一键启动 |

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

---

## 5. 目录结构（目标形态，随阶段逐步落地）

```
project_root/
├── app/
│   ├── __init__.py
│   ├── main.py                    # FastAPI 入口：注册路由、全局异常、日志中间件
│   ├── config/
│   │   ├── __init__.py
│   │   ├── settings.py            # pydantic-settings 读取 .env，集中配置
│   ├── routers/
│   │   ├── __init__.py
│   │   ├── document.py            # 文件上传/解析接口（第一阶段）
│   │   ├── knowledge_base.py      # 知识库管理接口（第四阶段）
│   │   └── chat.py                # RAG 问答 SSE 接口（第五阶段）
│   ├── service/
│   │   ├── __init__.py
│   │   ├── document_service.py    # 文档上传/解析/清洗编排（第一阶段）
│   │   ├── parser/
│   │   │   ├── __init__.py
│   │   │   ├── base.py            # DocumentParser 抽象接口（可扩展 OCR 等）
│   │   │   ├── txt_parser.py      # txt 解析
│   │   │   └── pdf_parser.py      # pdfplumber 解析，逐页提取
│   │   ├── embedding_service.py   # Embedding 抽象（第三阶段）
│   │   ├── chunk_service.py       # 分块：chunk_size + overlap（第二阶段）
│   │   ├── vector_service.py      # Milvus 操作封装（第三阶段）
│   │   └── rag_service.py         # 问答编排：召回+拼prompt+SSE（第五阶段）
│   ├── models/
│   │   ├── __init__.py
│   │   ├── schemas.py             # Pydantic 请求/响应模型
│   │   └── orm/                   # SQLAlchemy 表结构（第二阶段起）
│   │       ├── __init__.py
│   │       ├── knowledge_base.py
│   │       ├── document.py
│   │       └── chunk.py
│   └── utils/
│       ├── __init__.py
│       ├── clean_text.py          # 文本清洗（可配置开关）
│       ├── exceptions.py          # 业务异常 / 系统异常定义
│       ├── response.py            # 统一返回体 {code, msg, data}
│       ├── logger.py              # 全局日志（记录入参/文件名/异常堆栈）
│       └── file_utils.py          # 文件校验、uuid 重命名、保存
├── uploads/                       # 上传文件存储目录（.gitignore）
├── logs/                          # 日志目录（.gitignore）
├── requirements.txt
├── .env.example                   # 环境变量模板（提交仓库）；.env 为本地真实配置（gitignore）
├── .gitignore
└── README.md
```

---

## 6. 核心设计决策（含修正项记录）

### 6.1 PDF 解析：pdfplumber（修正项）

- 原方案 PyPDF2 已进入维护模式，复杂排版/表格提取质量差，**改用 pdfplumber**（备选 PyMuPDF/fitz）。
- 通过 `DocumentParser` 抽象接口屏蔽解析器差异，后续扩展 OCR 解析器（扫描版）时上层业务零改动。
- **扫描版 PDF 策略（第一阶段）**：逐页提取后文本为空或极少 → 抛业务异常「暂不支持扫描版 PDF」。该策略为临时方案，后续可用 OCR（如 PaddleOCR）扩展，接口已预留扩展位。

### 6.2 Embedding：独立抽象，模型待定（修正项）

- **deepseek-harness 是对话/生成服务，不提供 embedding 接口**，文档向量化和问题向量化必须单独选模型。
- 首选：本地部署 bge-m3 / bge-large-zh-v1.5（sentence-transformers，中文效果好）；备选：OpenAI 兼容 embedding 服务。
- 架构上必须抽象 `EmbeddingService` 接口，实现可切换。
- ⚠️ Milvus collection 的 **dim 维度与 embedding 模型强绑定**：第一阶段定下模型/维度后，后续换模型需重建 collection。此决策在第三阶段前必须敲定。

### 6.3 MySQL + Milvus 双写一致性（工业级关键考点）

- 入库顺序：**先写 MySQL**（落库即拿到 chunk_id）→ **再写 Milvus**（向量 id 与 chunk_id 一一对应）→ 任一步失败走**补偿删除**。
- 删除顺序：先删 Milvus 向量 → 再删 MySQL 记录（或 MySQL 软删 + 定时清理任务兜底）。
- 面试必答：MySQL 有记录但 Milvus 没向量的排查与恢复方案（对账任务）。

### 6.4 SSE 流式协议（与统一返回体分开）

- 普通 JSON 接口：统一返回体 `{code, msg, data}`。
- **SSE 流式接口不使用该信封**，改用事件协议：
  - `event: start` → 元信息 + 溯源信息（文档名称、原文片段）
  - `event: delta` → 逐 token 输出
  - `event: done` → 结束，含 code/msg
- 接口文档中对流式接口单独说明。

### 6.5 文件存储与命名

- 磁盘文件名用 `uuid4.hex`，原始文件名存数据库/元数据，规避中文文件名与路径穿越问题。
- 上传目录、日志目录均从 .env 读取，可配置。

### 6.6 Milvus 引入时机

- Milvus standalone 部署依赖 etcd + MinIO，内存 2~4GB 起，**第一阶段不安装**，第二阶段末/第三阶段再引入 docker-compose。
- 第一阶段接口与设计中不出现任何向量库逻辑（用户约束）。

---

## 7. 开发规则（硬性约束）

1. 严格按照模块分阶段开发，**禁止一次性生成全部完整项目代码**；一个模块完成经确认后，再开发下一阶段；每写完一块代码附带核心逻辑讲解。
2. 偏工业后端思路：必须考虑边界情况、异常捕获、参数校验，拒绝玩具 demo 代码。
3. 代码注释完整，关键函数增加 docstring，每段代码附原理讲解（逐行看懂，用于面试讲解）。
4. 每个阶段完成后输出：**目录结构、接口文档、curl 测试命令、本模块设计思路、下一阶段改造扩展点**。
5. 所有接口参数全部使用 Pydantic 强校验。
6. 日志打印关键信息：接口入参、文件名称、异常堆栈。
7. **版本管理约定**：每个阶段完成 → 提交并推送到 `dev` 分支 → 用户确认无误后 → 合并到 `main` 并推送远程。未经用户确认不合并 main。

---

## 8. 阶段计划与进度跟踪

### 8.0 阶段总览

| 阶段 | 内容 | 状态 |
|---|---|---|
| 第一阶段 | 项目骨架 + 文件上传解析模块 | ✅ 已完成 |
| 第二阶段 | 文本分块 + MySQL 元数据存储 | ✅ 已完成 |
| 第三阶段 | Embedding 接入 + Milvus 向量入库 | ⬜ 未开始 |
| 第四阶段 | 知识库管理接口（含级联删除） | ⬜ 未开始 |
| 第五阶段 | RAG 问答接口（召回 + SSE 流式 + 溯源） | ⬜ 未开始 |
| 第六阶段 | 工程稳定性优化 | ⬜ 未开始 |
| 第七阶段 | 容器部署（Dockerfile + docker-compose） | ⬜ 未开始 |

> 状态标记：⬜ 未开始 ｜ 🟡 进行中 ｜ ✅ 已完成

### 8.1 第一阶段：项目骨架 + 文件上传解析模块

**范围约束：本阶段不实现 Milvus、分块、问答逻辑。**

#### 任务清单

- [x] 1. 项目骨架：目录结构、`main.py` 入口、`config/settings.py` + `.env.example`（✅ 2026-08-20，含 README/.gitignore，已实测启动）
- [x] 2. 统一返回体 `{code, msg, data}` + 全局异常捕获（区分业务异常/系统异常，异常打印完整堆栈日志）（✅ 2026-08-20，404/health 实测通过）
- [x] 3. 全局日志：记录接口入参、文件名称、异常堆栈（✅ 2026-08-20，logger + 请求日志中间件 + 滚动文件落盘）
- [x] 4. 文件上传接口（✅ 2026-08-20，4 种场景 curl 实测通过）：
  - [x] 支持 txt、可复制文本 PDF（后缀白名单放行；扫描版 PDF 检测在任务5解析时实现）
  - [x] 后缀名校验、文件大小校验（单文件 ≤ 20MB，流式累计字节数权威判定）
  - [x] 重复文件名策略：uuid 自动重命名，避免覆盖
  - [x] 保存到本地指定目录（路径来自 .env）
- [x] 5. 文件解析（✅ 2026-08-20，txt/文本PDF/扫描版 3 类实测通过）：
  - [x] txt：直接读取文本（UTF-8/GBK 自适应编码）
  - [x] PDF：pdfplumber 逐页提取文字（DocumentParser 抽象，含扫描版检测）
  - [x] 文本清洗：去除连续多个换行符、多余空白空格、不可见乱码字符，保留合理段落换行；独立工具函数 + .env 可配置开关；记录清洗前后字符数对比日志
- [x] 6. 上传接口同步完成解析，返回：文件id、原始文件名、文件大小、清洗后文本预览片段、总字符数（✅ 2026-08-20，解析失败自动清理落盘文件）
- [x] 7. 基础依赖文件 `requirements.txt`（✅ 提前至骨架阶段完成）
- [x] 8. uvicorn 启动服务（✅ README 已含启动命令，`/health` 实测 200）

#### 阶段交付物

- [x] 目录结构（见阶段讲解输出）
- [x] 接口文档（见阶段讲解输出）
- [x] curl 测试命令（见阶段讲解输出）
- [x] 本模块设计思路讲解（见阶段讲解输出）
- [x] 下一阶段改造扩展点（见阶段讲解输出）

### 8.2 第二阶段：文本分块 + MySQL 元数据存储（✅ 2026-08-21）

- ✅ 固定 `chunk_size` + `overlap` 重叠滑动窗口，参数走 .env 配置（默认 500/50）。
- ✅ 讲解 chunk 大小、overlap 各自作用与调参思路（见本阶段讲解输出）。
- ✅ MySQL 三表结构落地：`knowledge_bases` / `documents` / `chunks`（SQLAlchemy 2.x ORM，
  启动时自动建库建表；`chunks.vector_id` 预留为 NULL，第三阶段写入 Milvus 向量 id）。
- ✅ 上传全链路接入：上传 → 解析 → 清洗 → 分块（按页携带页码）→ 元数据+分块单事务落库；
  响应新增 `chunk_count` 字段。
- ✅ 连接池配置：pool_pre_ping / pool_recycle / max_overflow；MySQL 不可用时服务降级启动。
- ⚠️ 待办（后续阶段）：文档/知识库管理接口（第四阶段）；Alembic 迁移替代 create_all（第七阶段）。

### 8.3 第三阶段：Embedding + Milvus 向量入库（预留）

- 敲定 embedding 模型与维度（见 6.2），创建 Milvus collection。
- 文档入库：分块 → 向量化 → 双写 MySQL + Milvus（见 6.3）。

### 8.4 第四阶段：知识库管理接口（预留）

- 新建 / 查询 / 删除知识库。
- 删除文档时，同步删除 Milvus 对应向量 + MySQL 全部对应 chunk 记录（级联删除 + 补偿）。

### 8.5 第五阶段：RAG 问答接口（预留）

- 用户问题向量化、Milvus 召回 top-k 相关文本块。
- 组装系统提示词 + 检索上下文 + 用户问题。
- SSE 流式返回大模型回答，附溯源信息（文档名称、原文片段），协议见 6.4。

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

| 日期 | 版本 | 变更内容 | 原因 |
|---|---|---|---|
| 2026-08-20 | v0.1 | 初版：基于原始方案 + 评审修正 | PDF 解析改用 pdfplumber；新增 embedding 抽象、双写一致性、SSE 协议、Milvus 引入时机等设计决策；建立进度跟踪机制 |
| 2026-08-20 | v0.2 | 骨架落地调整：`.env.example` 统一放项目根目录（原文档标在 `config/` 下）；`requirements.txt` 提前至骨架阶段 | 遵循 Python 项目惯例（`.env` 在根目录加载）；依赖文件是安装骨架的前提 |
| 2026-08-20 | v0.3 | 任务 2+3 合并开发（统一返回体 + 全局异常 + 全局日志，二者耦合无法拆分）；`/health` 也套统一信封 | 任务 2 要求"异常打印完整堆栈日志"，必须先有全局日志设施；接口格式一致性 |
| 2026-08-20 | v0.4 | 任务 4 上传接口完成：新增 `utils/file_utils.py`、`models/schemas.py`（泛型信封 `ApiResponse[T]`）、`service/document_service.py`、`routers/document.py` | 上传校验 + 落盘 + 响应契约；解析与 preview/char_count 留待任务 5/6 填充 |
| 2026-08-20 | v0.5 | 任务 5+6 完成，第一阶段收官：DocumentParser 抽象 + txt/pdf 解析器 + 扫描版检测 + clean_text 可配置清洗 + 上传全链路（preview/char_count 填充）；解析失败自动清理落盘文件；新增 `requirements-dev.txt`（fpdf2 测试工具） | 完成第一阶段全部任务；修复"解析失败残留文件"问题；清洗/预览配置入 .env |
| 2026-08-20 | v0.6 | 新增版本管理约定（开发规则第 7 条）：阶段完成推 dev → 确认后合 main 再推远程；远程 dev 分支已创建 | 用户指定分支工作流 |
| 2026-08-21 | v0.7 | 第二阶段完成：chunk_service（滑动窗口 + 按页分块 + 边界校验）+ MySQL ORM 三表 + 上传全链路落库（单事务）+ 响应新增 chunk_count；修复建库 URL 与引擎缺库名两个 bug | 完成第二阶段；真实 MySQL 全链路验证通过 |

> 后续任何方案调整：在此表追加一行，并同步修改正文对应小节。
