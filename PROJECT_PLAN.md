# 企业知识库 RAG 后端系统 — 开发计划与进度跟踪

> 开发以本文档为准，任何方案调整都先改这里（在「变更记录」登记），每个阶段完成后更新「进度跟踪」。
>
> 当前版本：v1.3 ｜ 创建日期：2026-08-20 ｜ 最近更新：2026-08-28

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
| PDF 解析 | **pdfplumber** |
| 文本解析 | 内置 open() 读取 | txt 直接读取 |
| 向量库 | Milvus | 只存 embedding 向量，与 MySQL 元数据一一关联 |
| 元数据库 | MySQL | 知识库、文档、chunk 元数据 |
| Embedding | **bge-m3** | 本地 sentence-transformers 加载，1024 维；|
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
├── deploy/
│   └── docker-compose.milvus.yml  # Milvus 单机部署（etcd+MinIO+standalone，第三阶段）
├── uploads/                       # 上传文件存储目录（.gitignore）
├── logs/                          # 日志目录（.gitignore）
├── PROJECT_PLAN.md                # 本计划文档
├── TECH_DESIGN.md                 # 技术设计与面试要点文档
├── requirements.txt
├── requirements-dev.txt           # 测试工具依赖（fpdf2 等）
├── .env.example                   # 环境变量模板（提交仓库）；.env 为本地真实配置（gitignore）
├── .gitignore
└── README.md
```

---

## 6. 核心设计决策

### 6.1 PDF 解析：pdfplumber

- 通过 `DocumentParser` 抽象接口屏蔽解析器差异，后续扩展 OCR 解析器（扫描版）时上层业务零改动。
- **扫描版 PDF 策略（第一阶段）**：逐页提取后文本为空或极少 → 抛业务异常「暂不支持扫描版 PDF」。该策略为临时方案，后续可用 OCR（如 PaddleOCR）扩展，接口已预留扩展位。

### 6.2 Embedding：独立抽象，模型已定 bge-m3

- **本地部署 bge-m3（1024 维，sentence-transformers 加载）**。理由：多语言 + 8K 长文本、中文检索效果强、与 16G 独显（cuda 推理）匹配；备选：bge-large-zh-v1.5（更轻）、OpenAI 兼容 embedding 服务。
- 架构上必须抽象 `EmbeddingService` 接口，实现可切换。
- ⚠️ Milvus collection 的 **dim 维度与 embedding 模型强绑定**：定下 bge-m3/1024 后，后续换模型需重建 collection。

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
7. **版本管理约定**：每个阶段完成 → 提交并推送到 `dev` 分支；`dev → main` 的合并与推远程由**用户自行执行**（AI 只推 dev）。

---

## 8. 阶段计划与进度跟踪

### 8.0 阶段总览

| 阶段 | 内容 | 状态 |
|---|---|---|
| 第一阶段 | 项目骨架 + 文件上传解析模块 | ✅ 已完成 |
| 第二阶段 | 文本分块 + MySQL 元数据存储 | ✅ 已完成 |
| 第三阶段 | Embedding 接入 + Milvus 向量入库 | ✅ 已完成 |
| 第四阶段 | 知识库管理接口（含级联删除） | ✅ 已完成 |
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

**三表建表 SQL（与实际数据库一致的权威版本；已按此设计建表，`init_db()` 的 `create_all` 只在表不存在时创建，不会改动已存在的表）**

```sql
-- 知识库表：文档的顶层容器
CREATE TABLE knowledge_bases (
  id              INT AUTO_INCREMENT PRIMARY KEY COMMENT '主键',
  name            VARCHAR(64)  NOT NULL UNIQUE COMMENT '知识库名称',
  description     VARCHAR(255) NULL COMMENT '描述',
  owner_id        INT NULL COMMENT '所属用户ID',
  embedding_model VARCHAR(64)  NULL COMMENT '嵌入模型名称',
  chunk_strategy  VARCHAR(32)  NULL COMMENT '分块策略(fixed/semantic/sentence)',
  chunk_size      INT NULL COMMENT '分块大小(字符数)',
  chunk_overlap   INT NULL COMMENT '分块重叠(字符数)',
  doc_count       INT NOT NULL DEFAULT 0 COMMENT '文档数量',
  status          TINYINT NOT NULL DEFAULT 1 COMMENT '状态: 0-禁用 1-启用',
  updated_at      DATETIME NULL COMMENT '更新时间',
  created_at      DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  KEY ix_kb_owner_id (owner_id),
  KEY ix_kb_status (status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='知识库（对应一个文件夹，是文档的顶层容器）';

-- 文档表：上传文件的元数据记录
CREATE TABLE documents (
  id                INT AUTO_INCREMENT PRIMARY KEY COMMENT '主键',
  kb_id             INT NULL COMMENT '知识库ID',
  file_id           VARCHAR(64)  NOT NULL UNIQUE COMMENT '上传返回的文件ID（uuid存储名）',
  original_filename VARCHAR(255) NOT NULL COMMENT '原始文件名',
  file_type         VARCHAR(32)  NULL COMMENT '文件类型(pdf/docx/txt/md等)',
  file_size         BIGINT       NOT NULL COMMENT '文件大小（字节）',
  char_count        INT NOT NULL COMMENT '清洗后总字符数',
  chunk_count       INT NOT NULL COMMENT '分块数量',
  status            TINYINT NOT NULL DEFAULT 0 COMMENT '处理状态: 0-待解析 1-解析中 2-解析完成 3-失败',
  parse_error       TEXT NULL COMMENT '解析失败原因',
  created_at        DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  updated_at        DATETIME NULL COMMENT '更新时间',
  KEY kb_id (kb_id),
  KEY ix_doc_status (status),
  KEY ix_doc_file_type (file_type),
  CONSTRAINT fk_documents_kb FOREIGN KEY (kb_id) REFERENCES knowledge_bases(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='文档（对应一个上传的文件，属于某个知识库）';

-- 分块表：检索最小单元，与 Milvus 向量一一对应
CREATE TABLE chunks (
  id               INT AUTO_INCREMENT PRIMARY KEY COMMENT '主键',
  doc_id           INT NOT NULL COMMENT '所属文档ID',
  kb_id            INT NULL COMMENT '知识库ID',
  chunk_index      INT NOT NULL COMMENT '文档内块编号（从0开始）',
  content          TEXT NOT NULL COMMENT '块原始文本',
  token_count      INT NULL COMMENT 'token数量',
  embedding_status TINYINT NOT NULL DEFAULT 0 COMMENT '嵌入状态: 0-待嵌入 1-已嵌入 2-失败',
  page_number      INT NOT NULL COMMENT '来源页码（从1开始）',
  vector_id        VARCHAR(64) NULL COMMENT 'Milvus向量ID（与chunk id一一对应）',
  created_at       DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  KEY kb_id (kb_id),
  KEY ix_chunks_doc_id (doc_id),
  KEY ix_chunks_created_at (created_at),
  KEY ix_chunk_embedding_status (embedding_status),
  CONSTRAINT fk_chunks_doc FOREIGN KEY (doc_id) REFERENCES documents(id),
  CONSTRAINT fk_chunks_kb  FOREIGN KEY (kb_id)  REFERENCES knowledge_bases(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='检索片段（文档切分后的chunk，是检索和嵌入的最小单元）';
```

- ⚠️ 待办（后续阶段）：文档/知识库管理接口（第四阶段）；Alembic 迁移替代 create_all（第七阶段）。

### 8.3 第三阶段：Embedding + Milvus 向量入库（✅ 已完成）

- ✅ 敲定 embedding 模型 bge-m3（1024 维，见 6.2），创建 Milvus collection。
- ✅ 文档入库：分块 → 向量化 → 双写 MySQL + Milvus（见 6.3），失败补偿删除。
- ✅ 本地加载 bge-m3 权重（`EMBEDDING_MODEL` 指向本地路径），`EMBEDDING_DEVICE=cuda` GPU 推理。

### 8.4 第四阶段：知识库管理接口（✅ 2026-08-28）

- ✅ 知识库增删查：`POST/GET/DELETE /api/v1/kbs`，`GET /api/v1/kbs/{id}`（name 唯一、Pydantic 强校验）；
- ✅ 文档删除：`DELETE /api/v1/documents/{file_id}`，级联清理 Milvus 向量 + MySQL chunks/documents + 磁盘文件；
- ✅ 知识库删除：级联清理其下所有文档（复用 `purge_document` 逐文档清理）；
- ✅ 上传挂知识库：`/upload?kb_id=` 可选参数，入库写 documents.kb_id / chunks.kb_id；
- ✅ 级联顺序要点：先 Milvus → 再 MySQL 子表（chunks）→ 再父表（documents/知识库）→ 最后磁盘文件；
  批量 `Query.delete()` 不触发 ORM 级联，必须显式先删子表；
- ✅ 真实环境验证：建库/去重(1003)/列表带 doc_count/详情带文档/删文档级联/删库级联/各类 1002 错误场景全部通过；
- ⚠️ 待办：Milvus 删除异步生效需理解 flush/compaction 语义；生产建议 Alembic（第七阶段）。

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
| 2026-08-21 | v0.8 | 新增 `TECH_DESIGN.md`：技术方案与面试要点文档（分层/上传/解析/清洗/分块原理/MySQL 表设计/连接池/事务/双写一致性/面试 Q&A/踩坑记录） | 沉淀技术方案供面试复习 |
| 2026-08-21 | v0.9 | 工作流调整：合 main + 推远程由用户自行执行（AI 只推 dev）；`TECH_DESIGN.md` 移除运维/环境层面琐碎问题记录 | 用户指定；文档只保留有讲解价值的代码设计与面试要点 |
| 2026-08-27 | v1.0 | 第三阶段完成：bge-m3（GPU）+ Milvus docker-compose 部署 + Embedding 抽象 + vector_service + 入库全链路（双写一致 + 补偿）；修复 pymilvus 3.0 API 兼容、load_collection 缺失、补偿删除孤儿 chunk 三个真实问题；文档头部增加版本/更新时间，目录结构同步 | 完成第三阶段；真实 Milvus + GPU 全链路验证通过 |
| 2026-08-27 | v0.10 | 第三阶段完成：bge-m3（1024 维）+ Milvus 向量入库全链路；环境切 conda `rag_kb`（GPU torch）并本地加载 bge-m3 权重 | 国内下载 GPU torch / bge-m3 权重过慢，改为手动下载 + 本地路径加载 |
| 2026-08-28 | v1.1 | 第四阶段完成：知识库增删查 + 文档删除级联（Milvus/MySQL/文件三层清理）+ 上传挂知识库；新增 knowledge_base_service/router | 完成第四阶段；级联删除顺序、name 唯一、错误场景全部实测通过 |
| 2026-08-28 | v1.2 | 字段一致性对齐：以实际数据库为准补齐 ORM（knowledge_bases 补 owner_id/embedding_model/chunk_strategy/chunk_size/chunk_overlap/doc_count/status/updated_at；documents 补 file_type/status/parse_error/updated_at；chunks 补 token_count/embedding_status）；代码接入这些字段（file_type/status=2/embedding_status=1/doc_count 上传自增删除自减）；PROJECT_PLAN DDL 更新为权威版本；新增 scripts/verify_schema.py 校验工具 | 修复 ORM/文档/实际库三方字段不一致 |
| 2026-08-28 | v1.3 | README 补全（第四阶段进度、接口清单、前端说明、环境注意）；新增第 11 节「前端页面设计」（单页 HTML，三个 Tab：知识库管理/文档上传/RAG 问答） | 完善项目文档与前端规划，待第五阶段后开发 |

> 后续任何方案调整：在此表追加一行，并同步修改正文对应小节。

---

## 11. 前端页面设计（极简单页，待第五阶段后开发）

**技术选型**：单页 HTML + 原生 JS（不引入构建工具/框架，保持"极简"）。页面由 FastAPI 以静态文件托管（`app/static/`），或直接双击 HTML 跨域调用后端接口（需后端开 CORS）。

**三个页面（或一个单页三 Tab）**：

| 页面 | 功能 | 调用接口 |
|---|---|---|
| 知识库管理 | 新建 / 列表 / 删除知识库 | `POST/GET/DELETE /api/v1/kbs` |
| 文档上传 | 选择知识库 + 上传文档 + 显示解析结果（字符数/分块数/预览） | `POST /api/v1/documents/upload?kb_id=` |
| RAG 问答 | 输入问题 → SSE 流式显示回答 + 溯源片段（文档名/原文/页码） | `POST /api/v1/chat`（SSE） |

**交互要点**：
- 问答页用 `fetch` + `ReadableStream`（或 `EventSource`）消费 SSE，逐 token 追加到界面，展示 `start/delta/done` 事件；
- 溯源片段以卡片展示（文档名称 + 原文 + 相似度/页码）；
- 知识库列表、文档列表刷新逻辑简单化，无需前端状态管理。

**开发顺序**：第五阶段 RAG 接口完成后，再做前端（否则无问答接口可调）。
