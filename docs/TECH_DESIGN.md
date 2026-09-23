# 企业知识库 RAG 后端 — 技术设计与面试要点

> 配套 `PROJECT_PLAN.md`（计划与进度）。本文档沉淀每个模块的**技术方案、设计理由、面试讲解要点**，随阶段持续更新。
> 阅读建议：面试前按章节过一遍，重点看「为什么这么设计」——面试官问的不是你写了什么，而是你为什么这么写。

---

## 1. 总体架构

### 1.1 分层架构（五层）

| 层 | 职责 | 红线 |
|---|---|---|
| config | 全部配置（.env 驱动，pydantic-settings） | 禁止硬编码 |
| routers | 只接收参数、调 service、包响应 | 不写业务逻辑 |
| service | 解析/清洗/分块/检索/问答等全部业务 | — |
| models | Pydantic 请求响应模型 + ORM 表结构 | — |
| utils | 清洗/日志/异常/文件等通用工具 | — |

**面试问「为什么这么分层」**：
1. **单一职责**：路由层薄、业务层厚，接口文档（OpenAPI）只暴露契约，业务可独立测试；
2. **可替换性**：换解析器、换向量库只动 service 层，routers/models 不动（面向接口编程）；
3. **团队协作**：前后端按 models 契约并行开发，接口层稳定。

### 1.2 统一返回体 `{code, msg, data}`

- `code=0` 成功；非 0 失败。业务码集中在 `RespCode` 常量类，禁止魔法数字。
- **HTTP 状态码策略（关键设计）**：
  - 业务异常 → **HTTP 200 + 非 0 code**（前端统一判断 `body.code`）；
  - 参数校验（422）、资源不存在（404）、系统异常（500）→ **保留真实 HTTP 状态码** + 统一 body。
- **为什么不全返回 200**：Nginx/负载均衡/监控/K8s 探活都依赖真实状态码感知故障。全 200 意味着"服务挂了监控也看不出"。
- **SSE 流式接口例外**：不用信封，用事件协议 `start`（元信息+溯源）→ `delta`（token 流）→ `done`（结束/错误码）。

### 1.3 异常体系

- `BizException`：**可预料的业务错误**（文件类型不支持、超限等）。全局处理器返回 HTTP 200 + 业务码，日志记 WARNING **不打堆栈**（预期内错误无排查价值）；
- `SystemException` / 未捕获异常兜底：返回 HTTP 500 + 通用提示，`logger.exception` **完整堆栈只进日志、不进响应**（防泄漏内部实现细节）；
- 处理器匹配按异常类型 MRO，具体类型优先；**兜底处理器保证任何异常下接口都返回统一结构的 JSON**，而不是框架默认纯文本报错。

---

## 2. 文件上传设计

### 2.1 校验三道防线（按成本从低到高）

1. **后缀名校验**（白名单来自 .env，转小写比对）——最便宜，先挡；
2. **流式大小校验**：分块读取（1MB/次）边读边累计字节数，**超限立即中断**并清理半成品；
3. **空文件拒绝**：0 字节无业务意义。

**为什么用流式累计而不是 Content-Length**：
- 部分客户端/代理不携带 Content-Length；
- 流式累计的字节数才是**权威值**（实际读了多少就是多少）；
- 超限提前止损，不会把 20MB+ 数据全读进内存再丢弃。

### 2.2 存储命名：`uuid4.hex + 原始后缀`

原始文件名**永不参与磁盘路径拼接**，三个理由：
1. **同名覆盖**：uuid 天然去重；
2. **中文/特殊字符**文件名在部分文件系统有兼容问题；
3. **路径穿越**：恶意 `../xxx` 构造对 uuid 命名免疫。

### 2.3 失败清理

解析/分块/入库任一环节失败 → **删除已落盘文件**，保证 uploads 目录不存在"没有数据库记录"的孤儿文件（全链路一致性）。

### 2.4 同名文件冲突策略（v1.21 决策：显式覆盖，已实施）

**现状（v1.8 起）**：同一知识库下 `original_filename` 同名 → 拒绝上传（`_check_duplicate` 抛业务异常）。原意是避免同名文件在 Milvus 里留下两套相同向量、检索结果成对重复。

**问题**：这条理由只能推出"不能放任重复"，推不出"必须拒绝"。企业场景下用户改了一版文件重新上传极常见，现状被迫先去文档列表删旧的。同名冲突的完整选项其实有四种：

| 策略 | 优点 | 代价 |
|---|---|---|
| A 拒绝（现状） | 安全，不会静默丢数据 | 体验差，强迫用户先删后传 |
| B 静默覆盖 | 体验最好 | 同名不同内容时静默丢数据、丢审计 |
| C 自动重命名（`手册(1).pdf`） | 不丢数据 | 恰好制造了 A 想避免的重复向量 |
| D 版本化（同 doc 多版本，检索只取最新） | 最正规 | 需改表结构 + 检索过滤，属独立阶段工作量 |

**决策：走"显式覆盖"**——冲突不静默，把决定权交给用户：

- 接口新增 `overwrite: bool = False`；为 `False` 时维持拒绝（安全默认），为 `True` 时执行替换；
- `_check_duplicate` 区分冲突语义；前端提供「同名文档处理成功后替换旧版本」确认勾选，确认后带 `overwrite=true` 上传；
- 覆盖流程复用已有的 `purge_document`，新任务成功后清理同库同名旧文档；处理中任务仍拒绝覆盖。

**实现要点（顺序是坑）**：

1. **必须先写新的、成功后再删旧的**。`purge_document` 注释已写明 Milvus 删除是异步生效的，而上传链路含解析 + embedding（首次还要懒加载 bge-m3，可达数十秒）。若写成"先删旧再解析新"：解析期间该文档在新旧两侧都查不到；新文件解析/入库失败时旧数据**永久丢失**。反过来最坏只是"短暂重复"，可检测、可用 `scripts/rebuild_vectors.py` 兜底——**重复可修复，丢失不可**。
2. `(kb_id, original_filename)` 目前**没有数据库唯一约束**（`sql/schema.sql` 只有 `file_id` 唯一），所以"先写后删"在数据库层面可行；同名校验是纯应用层规则。
3. `kb.doc_count` 要正确：替换需回退旧计数再 +1，可复用 `_compensate` 里 `greatest(doc_count - 1, 0)` 的写法。
4. 审计：当前没有版本表，覆盖即丢失历史。这也正是选"显式确认"而非静默覆盖的原因；若将来要求历史留痕，就是策略 D（版本化）。

**状态**：已在第九阶段异步入库流程上实现；新文档失败时旧文档仍保留，任务成功后才执行清理。

---

## 3. 解析器设计

### 3.1 DocumentParser 抽象 + 工厂注册表

- 上层只依赖 `DocumentParser.parse() -> ParseResult(text, page_texts)`；
- 新增格式（docx/OCR）= 写一个类 + 注册一行，**上层零改动**；
- `ParseResult.page_texts`（逐页文本）为分块的**来源页码**溯源预留数据。

### 3.2 扫描版 PDF 检测

- pdfplumber 逐页 `extract_text()`，全页提取不到文本（无文本层）→ 业务异常「暂不支持扫描版 PDF」；
- 部分空页（封面/目录）→ WARNING 容忍 30% 占比。
- 说明：这是第一阶段临时策略，后续可扩展 OCR（PaddleOCR）解析器，接口已预留。

### 3.3 txt 编码自适应

先 UTF-8 尝试解码，失败回退 GBK（Windows 常见），都失败才报错——比依赖 BOM 判断鲁棒。

---

## 4. 文本清洗设计

### 4.1 规则与顺序（顺序是考点）

1. **统一换行符** `\r\n | \r → \n`（必须先做，否则 `\r` 残留影响后续正则）；
2. 去不可见乱码（控制字符/零宽字符 U+200B~200F/BOM/替换符 U+FFFD，**保留 `\t\n`**）；
3. 行首行尾空白（MULTILINE 模式）；
4. 行内连续空格 2+ → 1；
5. 连续换行 3+ → 2（**保留段落间一个空行**的语义）；
6. 整体 strip。

**为什么顺序重要**：若先压缩换行再处理 `\r`，`\r\n` 会被当两个字符、压缩不彻底；若先去行首尾空白再压缩换行，带空白的空行会导致 `\n` 数量虚高。

### 4.2 可配置开关

每条规则对应 .env 开关（`CLEAN_REMOVE_INVISIBLE` 等），全关时原样返回不损耗数据。每次清洗记录**前后字符数对比日志**，用于排查解析质量。

---

## 5. 分块原理（面试重点）

### 5.1 chunk_size：检索粒度

- **作用**：每个块 = 一个检索单元 = 一个向量，平衡**检索精度**与**语义完整性**；
- **太大**（2000+ 字符）：块内多主题，向量语义被"平均化"，召回模糊、噪声大；拼进 LLM 上下文浪费 token；
- **太小**（100 字符）：单块信息量不足，向量表达不出完整语义，召回了但上下文残缺；
- **调参思路**：与 embedding 模型的语义窗口匹配。中文场景 **300~500 字符/块**是常见甜区（500 汉字 ≈ 200~300 token）；有清晰段落结构的文档按段落切（语义完整），无结构文本用定长滑动窗口。**看 recall@k 调，不拍脑袋**。

### 5.2 overlap：边界补偿

- **问题**：一句话/概念被恰好切成两半，两半各自语义不完整，召回丢关键信息；
- **解法**：相邻块**共享一段文本**（重叠区），被切断的语义在某个块内始终完整；
- **取值**：chunk_size 的 **10%~20%**。太小（5%）几乎无效；太大（50%）相邻块大量冗余，召回重复、浪费 token；
- **调参**：观察高频实体/关键句是否常被切在边界且召回丢失——丢了就加大 overlap。

**关系**：chunk_size 管粒度，overlap 管边界补偿；改了 chunk_size 要按比例重调 overlap。

### 5.3 为什么按页分块

- 页面是文档**自然边界**，每块有**唯一来源页码**，第五阶段溯源展示干净（前端显示"来自第 N 页"）；
- 代价：跨页的句子会被切开——可接受，页码明确性优先；
- 实现：遍历 `page_texts`，每页内部滑动窗口，`chunk_index` 文档内全局编号，`page_number` 从 1 开始。

### 5.3.1 结构化分块（第九阶段）

- MinerU 返回 `paragraph_title`、`text`、`table` 等结构块时，分块器按原始顺序消费结构块，不再把表格从页面文本中拦腰切断；
- 短块（包括表格）完整保留，只有超过 `chunk_size` 的块才使用滑动窗口切分；切分后的每个子块继承原块的 `block_type`、`heading_path` 和页码；
- txt、pdfplumber 或异常结果没有结构块时，自动回退原有按页滑窗逻辑，保证旧解析器和历史行为兼容；
- `heading_path` 写入 `chunks` 时序列化为 JSON 字符串，字段允许为空，避免把解析器专属结构耦合进 Milvus schema。

### 5.4 边界处理（写代码时容易漏的）

- 空文本 → 空列表；
- `overlap < 0 或 >= chunk_size` → **抛业务异常**（窗口不前进会死循环）；
- 末尾不足块长 → 直接收尾；
- `start = max(end - overlap, start + 1)` 兜底保证窗口**至少前进 1 字符**。

---

## 6. MySQL 表设计（面试重点）

### 6.1 三张表结构与字段理由（**DDL 见 `sql/schema.sql`**，此处为设计意图）

| 表 | 关键字段 | 设计理由 |
|---|---|---|
| knowledge_bases | id, name(唯一), description, created_at | 知识库容器，第四阶段提供管理接口；name 唯一防重名 |
| documents | id, kb_id(可空), **file_id(唯一)**, original_filename, file_size, char_count, chunk_count, created_at | file_id 唯一 = 上传接口返回的 uuid，防重复入库；kb_id 可空 = 第四阶段才接入知识库归属 |
| chunks | id, doc_id(FK), chunk_index, content(TEXT), page_number, **vector_id(可空)**, created_at | 检索最小单元；vector_id 第三阶段写入 Milvus 向量 id，实现 MySQL↔Milvus 一一对应 |

### 6.2 规范化 vs 反规范化（高频追问）

- **"文档名称"放 documents 表，chunks 用 doc_id 外键**，不冗余进 chunks；
- 理由：同一数据只存一份，避免不一致（改名要改 N 处）；溯源时 JOIN 取名字，代价是**一次联表查询**（索引兜底，量级可控）；
- 面试答法：数据一致性优先于"少写一条 JOIN"，反规范化只在**读多写少且热点查询**时才考虑（如缓存文档名到 chunk）。

### 6.3 连接池参数（为什么这么配）

- `pool_size=5, max_overflow=10`：常驻 5 连接 + 峰值最多扩到 15，控制资源占用；
- `pool_pre_ping=True`：**取连接前先探活**——MySQL 断连（重启/网络抖动）后连接池里的旧连接是死的，不探活就直接用会报错；
- `pool_recycle=3600`：MySQL 默认 `wait_timeout=8h` 会**主动断开空闲连接**，必须提前回收重建（1h 小于 8h）。

### 6.4 单事务写入

documents + chunks **同一事务**：`add(doc) → flush()（拿自增 id）→ 循环 add(chunk) → commit()`，失败 `rollback()`。保证不会出现"有文档没分块"的中间状态。

### 6.5 双写一致性（MySQL + Milvus，第三阶段落实，对账机制 2026-09-01 落地）

- 入库：**先 MySQL 落库**（拿到 chunk_id）→ **再写 Milvus**（向量 id 与 chunk_id 一一对应）→ 任一步失败**补偿删除**；
- 删除：先删 Milvus 向量 → 再删 MySQL 记录（或软删 + 定时清理兜底）；
- **面试必答**："MySQL 有记录但 Milvus 没向量"→ 对账任务（定期比对两边 id，差异补偿）。

**对账+补偿的三层时机（面试讲这套）**：

```
① 写路径（实时）：入库 Milvus 失败 → _compensate 回滚 MySQL
   （生产进阶：不删 MySQL，改置 chunks.embedding_status=2 → 重试队列）
② 读路径（查询兜底）：召回为空但有文档 → 判定向量丢失 →
   后台触发 rebuild_documents(doc_ids) + 明确提示（已实现）
③ 后台定时：调度器定期比对 MySQL(embedding_status=1) 与 Milvus id 集合，
   差异 doc → 调 rebuild_documents（第六阶段接 APScheduler）
```

- 核心逻辑已抽为 `vector_rebuild_service.rebuild_documents(doc_ids)`（幂等、纯增量），CLI（`scripts/rebuild_vectors.py`）、定时器、查询兜底三方复用；
- 查询兜底的关键判定：**Milvus 检索只要 scope 里有向量就必返回 top_k**，因此"召回完全为空 + MySQL 有文档"必然等于"向量全丢"，不会误判；
- 教训：Milvus 集合可能在服务运行期被外部删除，`ensure_collection` **不能做进程内"已就绪"缓存**，必须每次真查（真实踩过：缓存标志骗过检查导致持续 collection not found）。
- 教训 2（对称的一条）：**"清理"类操作必须对"目标不存在"幂等**。`delete_by_doc` 在 collection 不存在时应直接返回（无向量可删 ≠ 出错），否则"集合被删/数据卷重置"这种可自愈的状态，会被重试前的清理步骤抛成 `MilvusException code=100`，把一次本可成功的入库任务判死；同理，清理必须排在 `ensure_collection()` **之后**——顺序反了就等于拿"集合还不存在"当失败条件。

### 6.6 字段设计：为异步管线预留的状态字段（第四阶段对齐）

实际表比基础版多出一组「状态/配置」字段，反映最初设计里**异步管线**的意图：

| 字段 | 含义 | 设计意图 |
|---|---|---|
| `documents.status` (0待解析/1解析中/2完成/3失败/4降级完成) + `parse_error` | 解析状态 + 失败原因 | 支持异步解析（上传后后台处理，前端轮询状态）；降级完成独立于失败 |
| `chunks.embedding_status` (0待嵌入/1已嵌入/2失败) | 向量化状态 | 单独跟踪每个 chunk 的嵌入进度，失败可精准重试 |
| `knowledge_bases.embedding_model / chunk_strategy / chunk_size / chunk_overlap` | 每库独立配置 | 不同知识库用不同模型/分块策略（覆盖全局默认） |
| `knowledge_bases.owner_id` | 归属用户 | 多租户/多用户隔离铺路 |
| `knowledge_bases.doc_count` | 冗余文档数 | 反规范化，列表免 COUNT join |

当前实现是**同步管线**（上传内完成解析+嵌入，成功即 status=2 / embedding_status=1），所以这些状态字段在成功路径上直接跳到终态；字段本身为将来改异步保留了扩展空间。`doc_count` 是唯一真正被用到的冗余列（上传自增、删除自减，list 直接读取，免 COUNT）。

第九阶段第一步新增 `chunks.block_type` 与 `chunks.heading_path`：前者记录 MinerU 结构块类型，后者以 JSON 数组字符串保存标题层级。字段允许为空，保证 txt/pdfplumber 等无结构解析结果及历史数据兼容；结构化分块器接入后再填充。

第九阶段异步任务使用独立的 `document_tasks` 表，不把重试次数和锁信息混入 `documents`：一个文档对应一个任务（`doc_id` 唯一），任务状态、`attempts`、`next_run_at`、`locked_at`、`last_error` 均可持久化。worker 后续按 `(status, next_run_at)` 索引领取任务，进程重启后可回收超时的 `processing` 任务并继续处理。

任务领取使用数据库事务和行锁：按 `next_run_at, id` 取最早任务，MySQL 8 使用 `FOR UPDATE SKIP LOCKED`，领取时原子更新为 `processing`、递增 `attempts` 并写 `locked_at`。超过锁超时的 `processing` 任务可被重新领取；处理失败但未达到 `max_attempts` 时按退避时间回到 `pending`，达到上限才进入 `failed`，并同步把文档标记为失败。这样 worker 进程崩溃不会永久丢任务，多 worker 也不会同时消费同一任务。

第九阶段将 HTTP 上传与重处理解耦：上传只落盘、写 `documents(status=0)`、创建 `document_tasks` 后立即返回，worker 才执行 MinerU、清洗、结构化分块、Embedding 和 Milvus 双写；前端通过 `GET /api/v1/documents/{file_id}/status` 轮询终态。文件 SHA-256 与解析器配置生成缓存键，缓存只保存原始 `ParseResult`，分块仍按当前配置重新计算。MinerU 的表格/图片/公式结构块写入 `assets` manifest，删除文档时同时清理对应资产目录。

worker 每次处理前先确保 collection 存在、再按文档删除已有 Milvus 向量，失败时再次补偿删除；因此任务重试是幂等的，不会因上一次在向量写入阶段崩溃而留下重复召回结果。解析与向量化可能持续数分钟，写入前会再 `ensure_collection()` 一次，覆盖"期间集合被外部删除"的窗口。

---

## 7. 日志与可观测性

- **滚动文件**：RotatingFileHandler，10MB/个 × 5 个备份，防日志无限膨胀（生产日志必须滚动）；
- **文件格式带文件名行号** `(file.py:42)`，线上排查定位到行；
- **请求日志中间件**：每个请求记 `方法 路径 -> 状态码 (耗时ms)`，异常打完整堆栈；
- 日志级别、目录全部 .env 可配；
- **时区必须与 MySQL 成对设置**（容器部署 v1.43）：日志时间 `%(asctime)s` 走 `time.localtime`、业务时间戳走 `datetime.now()`，两者都取**进程本地时区**；而 `created_at` / `next_run_at` 的默认值由 MySQL 侧 `DEFAULT CURRENT_TIMESTAMP` 生成（`time_zone=SYSTEM`，跟随容器时区）。所以 compose 里 `backend` 与 `mysql` 的 `TZ` 必须同值（默认 `Asia/Shanghai`）——只改一边，同一行内 `created_at` 与 `updated_at` 会差 8 小时，比"两边都偏 UTC"更难排查；
- **两条日志通道各有不可替代项**：stdout（`docker logs`）独有 uvicorn 的访问行——`uvicorn.access` 的 logger 是 `propagate=False`，不会经过根 logger 的文件 handler；而 `logs/app.log` 独有文件名行号与滚动留存（容器删了文件仍在，便于回查历史）。

---

## 8. 面试追问 Q&A（背熟）

**Q1：为什么返回体用 code，业务错误还返回 HTTP 200？**
A：HTTP 状态码是**传输层语义**（请求是否被正确处理），业务码是**业务层语义**（结果如何）。业务错误本质是"请求被正确处理了，但业务上不满足"，用 200 + code 让前端统一判断；而参数错误/系统错误保留真实 4xx/5xx，让监控、Nginx、探活能感知故障。

**Q2：为什么上传用 uuid 重命名而不是保留原名？**
A：三个问题一次解决——同名覆盖、中文/特殊字符兼容、`../` 路径穿越。原始文件名只作展示，存数据库，永不参与磁盘路径拼接。

**Q3：chunk_size 怎么定？overlap 为什么 10%~20%？**
A：chunk_size 匹配 embedding 语义窗口，中文 300~500 字符甜区，看 recall@k 调。overlap 是边界补偿，10% 以下补偿不足（边界语义仍会丢），50% 以上相邻块冗余、召回重复内容浪费 token，10%~20% 是经验平衡点。

**Q4：为什么按页分块？跨页句子被切开怎么办？**
A：页面是自然边界，保证每块有唯一来源页码，溯源展示干净。跨页切断的代价换取页码明确性；如果未来需要跨页块，可以改为"全文连续切 + 记录起止页码区间"，接口层面 ParseResult 已支持。

**Q5：连接池为什么配 pre_ping 和 recycle？**
A：pre_ping 防"死连接"——MySQL 断连后池里连接已失效，取用前探活避免报错；recycle 防"服务端主动断连"——MySQL 8h 空闲断开，1h 回收提前重建。两个参数解决两个不同的连接失效场景。

**Q6：为什么 documents 和 chunks 要一个事务？**
A：避免中间状态——"有文档没分块"的脏数据会导致文档管理、删除、检索全部出问题。事务保证原子性，flush 拿自增 id 是 SQLAlchemy 的标准两步写。

**Q7：MySQL 有记录但 Milvus 没向量怎么办？**
A：对账任务定期比对两边 id 集合，差异项补偿重写；写入时先 MySQL 后 Milvus，失败补偿删除。面试加分：提到"对账 + 补偿"说明你考虑过分布式一致性的工程解法。

**Q8：为什么用 create_all 而不是 Alembic？**
A：开发阶段表结构快速迭代，create_all 够用且幂等；生产/多人协作需要**版本化迁移**（记录每个 schema 变更、可回滚、可审计），第七阶段引入 Alembic 替换。

---

## 9. Embedding 与 Milvus 向量库（第三阶段）

### 9.1 EmbeddingService 抽象（面试点）

- 抽象 `embed_texts / embed_query / dim`，换模型（bge-large、远端 API）只换实现不动上层；
- `embed_query` 单独抽象：旧版 bge-large/small 查询需加指令前缀「为这个句子生成表示以用于检索相关文章」，bge-m3 不需要——不同模型查询与文档的向量空间要一致，接口分开才能各自实现；
- `normalize_embeddings=True`（L2 归一化）+ Milvus COSINE 度量匹配：归一化后内积 ≡ 余弦，检索更稳；
- **懒加载 + 单例**：2GB 权重首次调用才加载（10s 级），进程内只加载一次（lru_cache）；
- 本地模型路径可配（`EMBEDDING_MODEL=D:\...\bge-m3`），离线可用，不依赖 HF 联网。

### 9.2 Milvus collection 设计（面试点）

- **主键 id = MySQL chunks.id（INT64）**：MySQL↔Milvus 一一对应，便于对账与溯源；
- **Milvus 只存向量 + 过滤字段**（doc_id/chunk_index/page_number），chunk 原文在 MySQL——元数据单一来源，避免双写不一致；检索命中后凭 id 回查 MySQL 取原文与页码（第五阶段溯源）；
- **COSINE 度量 + HNSW 索引**：语义检索标准组合，HNSW 是图索引，`M`（每个节点连接数，越大召回越高越耗内存）与 `efConstruction`（建图时候选集大小）可调；
- 过滤字段支持文档级检索/删除（`doc_id in [...]` 表达式），不用 partition 简化实现；
- **查询/检索前必须 `load_collection`**：Milvus 的 collection 需要加载进内存才能 search/query（建索引后也要 load），这是 Milvus 与普通数据库最大的使用差异，容易漏。

### 9.3 双写一致性落地（对应 6.5）

```
MySQL 落库（拿 chunk.id）→ 批量向量化 → 写 Milvus（主键=chunk.id）→ 回填 MySQL.vector_id
失败任一环 → _compensate：删 Milvus 向量 → 删 MySQL chunks → 删 documents → 删文件
```

- **先 MySQL 后 Milvus**：MySQL 是事实源，先落库拿到权威 id；
- **回填 vector_id**：标记该块已向量化，也是「两边一致」的可查询证据；
- **注意**：SQLAlchemy `Query.delete()` 是批量 SQL，**不触发 ORM 关系级联**——删除文档必须**先删子表 chunks 再删 documents**（或给外键配 `ON DELETE CASCADE`），否则产生孤儿数据。

### 9.4 环境与工程要点

- **GPU 推理**：`EMBEDDING_DEVICE=cuda`——首次调用含 CUDA 上下文初始化与 kernel autotune（约 0.3~0.4s），预热后单条约 13ms、批量 512 条约 2.8ms/条；CPU 则单条约 0.45s、批量约 31ms/条（相差一个数量级以上）。**微基准必须预热后再计时**，否则量到的是 CUDA 初始化而不是推理；
- **pymilvus 3.x API 差异**：`index_params` 从 dict 改为 `IndexParams` 对象（`pymilvus.milvus_client.index`），`search` 增加 `search_params` 显式参数——升级大版本时这类破坏性变更要靠真实验证暴露；
- 国内环境：HF 本体被墙走 `hf-mirror.com` 直连；新版 huggingface_hub 默认 Xet 存储后端（`cas-server.xethub.hf.co`）也被墙，需 `HF_HUB_DISABLE_XET=1` 强制走普通 HTTP。

---

## 10. 知识库管理与删除级联（第四阶段）

### 10.1 知识库接口设计

- `POST /api/v1/kbs` 新建：name 唯一（查重 → 重复抛 1003 业务异常），Pydantic 强校验（1~64 字符、description ≤255）；
- `GET /api/v1/kbs` 列表：LEFT JOIN + GROUP BY 统计每个库的文档数（`doc_count`）；
- `GET /api/v1/kbs/{id}` 详情：含文档列表；
- `DELETE /api/v1/kbs/{id}`：删除知识库 + 级联清理全部文档；
- 上传接口加可选 `kb_id`，入库写 `documents.kb_id` / `chunks.kb_id`（先校验库存在，不存在抛 1002）。

### 10.2 删除级联（面试重点）

**删除顺序（为什么这么排）**：

```
① Milvus 向量（delete_by_doc）  → 先删，避免"向量还在但元数据没了"
② MySQL chunks（先子表）
③ MySQL documents / knowledge_bases（后父表）
④ 磁盘文件（uploads/{file_id}{ext}）
```

**两个必须讲清的坑**：

1. **批量 `Query.delete()` 不触发 ORM 关系级联**：SQLAlchemy 里 `session.delete(doc)` 才会触发 `cascade="all, delete-orphan"`；而 `session.query(...).delete()` 是直接执行 SQL，**必须手动先删子表 chunks 再删父表 documents**，否则产生孤儿数据（这是我们真实踩过的）；
2. **Milvus 删除是异步生效的**：`client.delete()` 返回成功但数据要到 compaction/flush 才物理清除，`count(*)` 可能短暂仍显示旧值——理解这个语义才能解释"删了但数量没立刻变"。

**复用设计**：`purge_document(doc)` 是"清理单个文档全部分层"的唯一入口，文档删除和知识库删除都复用它，避免同一段级联逻辑写两遍（DRY）。

### 10.3 幂等与容错

- 每个删除环节单独 try/except：单点失败（如 Milvus 挂了）不阻断后续清理，只记 ERROR 日志——删除操作尽量"尽力而为"，不因一个依赖故障让整个删除失败卡住。
- 幂等的具体形态（v1.39）：`delete_by_doc` 先判 `collection_exists()`，集合不存在时记 INFO 并返回。删除的语义是"让目标不存在"，目标本来就不存在时成功返回才是正确语义；把它当异常抛出，等于让"Milvus 数据被重置"这种本可自愈的状态升级成文档处理失败。

---

## 11. RAG 问答与 SSE（第五阶段）

### 11.1 完整链路

```
用户提问 → embed_query（GPU）→ Milvus 召回 top-k
→ 相似度阈值过滤（RAG_MIN_SIMILARITY，防弱匹配答非所问）
→ 回查 MySQL 溯源（文档名/原文/页码）→ 组装系统提示词 + 上下文 + 问题
→ 大模型流式生成 → SSE start/delta/done
```

### 11.2 SSE 协议（面试点）

普通接口用 `{code,msg,data}` 信封，**流式接口例外**，用 SSE 事件：

```
event: start   data: [溯源片段{idx,doc_name,content,page,similarity}...]
event: delta   data: "回答增量文本"
event: done    data: {"code":0,"msg":"ok","answer":"完整回答","token_count":N}
```

- **start 先发溯源**：前端可先展示"引用了哪些文档"，再逐 token 追加回答；
- **done 带完整回答**：方便前端一次性拿到全文（复制/收藏）；
- 流中途异常：发错误 `done` 事件（code=500）收尾，**避免连接悬挂**；
- 反向代理需 `X-Accel-Buffering: no` 关闭缓冲，否则 token 不会实时到达。

### 11.3 大模型接入：httpx 手动解析 SSE（不依赖 openai SDK）

- DeepSeek 官方 API 是 OpenAI 兼容格式（`/chat/completions` + `Bearer key`），
  流式响应 `data: {...}\n\n` 逐行解析；
- **推理模型陷阱**：DeepSeek 带推理（v4/reasoner）的模型流式输出**先 reasoning_content（推理过程）后 content（回答正文）**——只透出 content，否则把"思考过程"当回答流给前端；
- 选 httpx 而非 openai SDK：控制力强（能看到每个原始事件）、已是依赖、无新增包；
- 超时：流式首 token 可能慢，read 给 120s，connect 10s。

### 11.4 防幻觉双保险（面试点）

1. **相似度阈值过滤**：Milvus 总是返回 top-k 条（即使相似度极低），`distance < RAG_MIN_SIMILARITY` 的弱匹配直接丢弃，避免把无关内容喂给模型；
2. **系统提示词约束**：只依据参考资料作答、无据明确答"未找到相关信息"、可用 [来源N] 标注——即使阈值没拦住，模型也会诚实拒绝编造。

### 11.5 流式并发与响应式注意

- 事件流中间件（请求日志）在 SSE 长连接上要避免缓冲/拦截；本实现 SSE 由 `StreamingResponse` 直接逐块写出；
- `rag_answer` 是异步生成器，embedding/search/trace 用 `run_in_threadpool` 避免阻塞事件循环，LLM 流式本身是异步 httpx。

### 11.6 稳定性保护（第六阶段）

- **输入长度**：问题同时经过字符上限和轻量 token 估算；拼好的参考资料 + 问题在发送给 LLM 前再次估算，超过 `LLM_MAX_INPUT_TOKENS` 直接返回业务错误，避免把超长上下文交给模型后才失败。
- **token 统计**：不在运行时下载各模型 tokenizer，`token_utils.estimate_token_count()` 对中文/非 ASCII 字符、ASCII 单词和标点做保守估算，日志和 SSE `done.token_count` 使用同一口径，适合容量保护而非计费。
- **LLM 重试**：只在首 token 前捕获可重试的超时/网络/5xx/429，按指数退避重试；已经向客户端输出正文后不重放，避免回答前后拼接两次。
- **限流与追踪**：单实例使用客户端 IP 的滑动窗口限流，响应带 `X-Trace-Id`；多实例部署时可把同一调用面替换为 Redis 等共享限流器。

### 11.7 Ollama 本地流式协议（第十阶段）

`LLM_PROVIDER=ollama` 时仍复用 `stream_chat()`，但请求切换到 Ollama 原生 `/api/chat`，逐行解析 JSON 的 `message.content`，并发送 `think=false`。这样可以明确丢弃 qwen3 的推理内容，只把回答正文转成现有 SSE `delta` 事件；`LLM_PROVIDER=deepseek` 仍走 OpenAI 兼容 `/chat/completions`。

---

## 12. 技术选型：自研编排 vs LangChain（设计决策记录）

> 决策：**RAG 主干采用原生库自研编排**（FastAPI + SQLAlchemy + pymilvus + sentence-transformers + httpx），不引入 LangChain 全家桶；生态中明显缺失的高级能力（Reranker、评估）后续按需引入。
> 本文记录决策依据，供复盘与面试讲解。

### 12.1 逐层对标

| RAG 环节 | 本项目（自研） | LangChain 等价物 |
|---|---|---|
| 文档加载 | `DocumentParser` 抽象 + 工厂注册表（`app/service/parser/`） | `PyPDFLoader` / `TextLoader` / `UnstructuredFileLoader` |
| 文本清洗 | `utils/clean_text.py`，规则可 .env 开关 | 无内置，需自写 transformer |
| 分块 | 手写滑动窗口 + **按页分块保留页码**（`chunk_service.py`） | `RecursiveCharacterTextSplitter`（更智能，默认不带页码） |
| 向量化 | `EmbeddingService` 抽象 + sentence-transformers 直调 | `HuggingFaceBgeEmbeddings` / `OpenAIEmbeddings` |
| 向量库 | pymilvus 手写 schema/index/load/filter（`vector_service.py`） | `langchain_milvus.Milvus`（VectorStore 封装） |
| 元数据存储 | **MySQL 单一事实源**，Milvus 只存向量 + 过滤字段 | 元数据塞进向量库 `metadata`，靠 filter 查 |
| 检索 | 手写 `search()` + `doc_id in [...]` 过滤 + 相似度阈值 | `as_retriever(search_type="similarity_score_threshold")` |
| 流程编排 | 手写 async generator（`rag_service.py`） | LCEL `prompt | llm | parser` / `RetrievalQA` |
| 提示词 | f-string 显式拼接 | `ChatPromptTemplate` |
| LLM 调用 | httpx 手写 SSE 解析（`llm_service.py`） | `ChatOpenAI(streaming=True)` |
| 溯源 | `_build_trace()` 回查 MySQL 取原文/页码/文档名 | `return_source_documents=True` |
| 流式协议 | 自定义 SSE `start/delta/done` | `astream_events()` 回调 |

### 12.2 选自研的四个决定性理由

**1. 数据一致性模型自研更强（最核心理由）**
本项目 MySQL 是元数据唯一事实源、Milvus 主键 = `chunks.id`，入库走「先 MySQL 拿 id → 再写 Milvus → 失败 `_compensate` 三级回滚」，两边 id 集合可直接对账（见 6.5）。LangChain 的 VectorStore 默认把元数据托管在向量库内，**不提供也不约束双写一致性与补偿**，要实现本项目这套对账语义反而要绕开其默认存储模型。

**2. 流式输出的细节可控**
DeepSeek 推理模型流式先吐 `reasoning_content`（思考过程）后吐 `content`（正文），`llm_service.py` 手动解析 SSE 只透出正文。用 `ChatOpenAI` 时推理内容落在 `additional_kwargs`，需另写自定义 parser 剥离——框架没有省事，还多一层。

**3. 栈浅，异常与兜底可定位**
本项目召回为空时的三级分支（向量丢失→后台重建并提示 / 范围内无文档→提示上传 / 阈值过滤后为空→换问法）都是显式代码，日志直接到行。LangChain 一次检索要穿过 `RunnableSequence → RunnableParallel → BaseRetriever` 多层抽象，异常常被包装吞掉，实现同等兜底需自定义 Retriever，表达更绕。

**4. 依赖与版本成本**
LangChain 依赖树庞大，且 0.1→0.2→0.3 多次破坏性升级（本项目在 pymilvus 2.x→3.x 的 `index_params`/`search_params` 变更上已体会过同类成本，见 9.4）。自研只用四个稳定底层库，升级面由自己控制。

### 12.3 承认 LangChain 的优势（决策不是否定框架）

- **搭 POC 快**：loader/splitter/vectorstore/chain 几行串完，原型阶段提速明显；
- **高级检索生态**：Reranker（bge-reranker）、BM25 + 向量混合检索（RRF 融合）、HyDE/查询改写、多轮记忆，均有现成集成；
- **评估生态**：ragas、LangSmith 等评测/可观测工具链成熟。

本项目当前「top-k=4 + COSINE 单阈值」的召回质量有明确上限，低于「向量粗排 20 → rerank 精排取 4」的两阶段方案——这是自研路线当前欠下的技术债，需在演进中偿还。

### 12.4 取舍总览

| 维度 | 自研（本项目选择） | LangChain |
|---|---|---|
| 可控性 / 报错定位 | 强（每步显式、栈浅） | 中（抽象层遮挡） |
| 原型搭建速度 | 慢 | 快 |
| 依赖与启动成本 | 轻 | 重 |
| 版本稳定性 | 自主控制 | 破坏性变更频繁 |
| 双写一致性 / 补偿 | 强（已落地） | 弱，需自建 |
| 高级检索 / 评估生态 | 暂无 | 丰富 |

### 12.5 演进路线：混合策略，而非二选一

保留自研主干不动，**只把真正缺失的零件从生态引入**：

1. 检索质量：接入 bge-reranker 做粗排→精排两阶段（优先，收益最大）；
2. 混合检索：加 BM25 稀疏召回 + RRF 融合，解决向量检索对专有名词/编号不敏感的问题；
3. 评估：引入 ragas 构建问答评测集，用 recall@k / 忠实度等指标驱动 chunk_size、阈值调参（替代拍脑袋）；
4. 引入方式仍遵循 `EmbeddingService` 式的抽象接口原则——框架组件被封装在 service 接口之后，可随时替换，不污染业务层。

### 12.6 面试答法（三句话）

1. **认同价值**：LangChain 原型提速明显，Reranker、评估等生态正是我们目前缺的；
2. **给出理由**：本项目的核心诉求是「数据可对账 + 流式可控 + 报错可定位」——MySQL↔Milvus 双写补偿和 `reasoning_content` 剥离用框架反而要写更多 custom 组件绕开默认行为；
3. **给出演进**：主干自研保持可控，检索增强与评估优先复用生态，**该自研的自研，该用轮子的用轮子**。

---

## 13. 本地 MinerU 接入（第八阶段）

### 13.1 私有部署边界（面试点）

- **MinerU 本地部署，不调用 MinerU 公有云 API**：企业 PDF 不出客户内网；
- 服务端口**只绑 `127.0.0.1`（回环）**，不暴露局域网；需要跨容器访问时才用内部 Docker 网络 + `--api-key`/认证反代；
- 镜像 `mineru:4` 由 MinerU 官方 `docker/china/Dockerfile` 构建，**模型权重已打进镜像**（`MINERU_MODEL_SOURCE=local`），运行时不联网；
- `uploads/` 作为原始文件仓库（解析、重试、降级、实验复现的数据源），不作为公网静态目录。

### 13.2 V1 API 作业流

MinerU 4.0 是**异步作业模型**，适配器（`MinerUParser`）按四步走：

```
① POST /v1/uploads            创建上传（返回 upload_url）
② PUT  {upload_url}           上传文件字节 → POST /v1/uploads/{id}/complete
③ POST /v1/parse/jobs         创建解析任务（tier + ocr_mode + output_formats）
④ GET  /v1/parse/jobs/{id}    轮询直到 completed/partial → 下载结果文件
   结果：structured_content（结构化 JSON）+ markdown
```

- 选 `structured_content` 是为了拿**块级结构**（`block.type` 区分 `paragraph_title`/`text`/`table` 等）+ 页码，供第九阶段结构化分块与溯源使用；
- markdown 作为全文来源（`ParseResult.text`）；
- 旧版 `/file_parse`、`/tasks` 路由在 4.0 不适用。

### 13.3 ParseResult 结构化扩展的兼容设计

`ParseResult` 从「`text` + `page_texts`」扩展为：

| 字段 | 说明 |
|---|---|
| `text` / `page_texts` | **保留不变**（旧代码、按页分块、清洗链路零改动） |
| `blocks: list[DocumentBlock]` | 结构化块：`block_type` / `content` / `page_number` / `block_index` / `heading_path` / `metadata` |
| `assets` | 图片/表格等素材（已声明，适配器暂未填充） |
| `parser_name` / `parser_version` | 解析器来源，便于线上排查与实验对比 |

**兼容策略**：新增字段全部可选（默认空/`unknown`），因此 pdfplumber、txt 解析器无需改动即可继续工作——**先扩契约、后接能力**，避免一次性大改。

### 13.4 解析器选择：配置驱动 + 降级保护

`get_parser(extension)` 是唯一入口，按格式分派：

| 格式 | 解析器 | 说明 |
|---|---|---|
| `.txt` / `.md` | `TxtParser` | 原生轻量，无需外部服务 |
| `.pdf` | `PDF_PARSER` 决定 | `pdfplumber`（基线）或 `MinerU`；选 MinerU 时包 `FallbackDocumentParser` |
| `.doc/.docx/.ppt/.pptx/.xls/.xlsx/.png/.jpg/.jpeg` | `MinerUParser` | 多格式由 MinerU（DocVortex）解析 |

**降级设计（`FallbackDocumentParser`）**：主解析器**抛异常或成功但输出无可用文本**（`page_texts` 全空）→ 记 WARNING → 用备用解析器解析 → 在 `ParseResult.metadata` 打标 `degraded/primary_parser/backup_parser/degrade_reason`；上层把降级原因写入 `documents.parse_error`，响应透出 `parser_name`/`degraded`。**原则：降级结果不伪装成完整解析**。

> 「成功但无文本」也要降级是真实踩坑（v1.44）：图形化排版 PDF（脑图/流程图）被 MinerU 整页识别为一张大图，接口返回 200 但 `structured_content` 零文本块、markdown 全是 `data:image/...;base64` 内嵌图——旧逻辑只在异常时降级，于是产出 0 分块的「成功」文档，入库却永远检索不到。判定标准用 `page_texts` 而非 `text`：分块按页切分，`text` 可能只有 base64 噪声。

> 注意：`except ... as exc` 块结束后 `exc` 会被 Python 删除，降级原因必须先在块内取成字符串。

**base64 图片剥离（`MinerUParser`）**：MinerU 的 markdown 可能内嵌整页 base64 图（几十万字符），会污染 `documents.char_count` / 预览 / 解析缓存；`_strip_base64_images` 用正则把 `data:image/...;base64,...` 载荷替换为 `[image]` 占位符后再使用。

**tier 取舍（v1.45 默认改 `advanced`）**：实测（脑图 PDF，1 页图形化排版）：`standard` 的版面模型把整页判成单个 `image` 区域直接渲染成图（`ocr_mode=ocr` 也救不了——OCR 只作用于文本区域），structured_content 零文本块；`advanced` 的 VLM 能把脑图转成 mermaid 结构文本（节点文字完整保留），与官方 API 质量一致。代价是 VLM 逐页推理、大文档解析更慢。`MINERU_TIER` 可在 `.env` / `deploy/.env` 覆盖回 `standard`（图形化文档仍有降级兜底走 pdfplumber）。

**MIME 推断**：MinerU 支持多格式，上传时 `mime_type` 必须按扩展名推断（`mimetypes.guess_type`），不能写死 `application/pdf`。

**端口与安全**：
- 本项目 FastAPI 占 8000，MinerU 服务映射到宿主 **8001**（`MINERU_API_URL=http://127.0.0.1:8001`）；
- compose 在 `deploy/docker-compose.yml` 的 `mineru` 服务（GPU 预留、`ipc: host`、放宽 memlock、只绑回环）；原独立 compose `deploy/docker-compose.mineru.yml` 已随统一 Compose 收口删除（v1.41），单起依赖用 `up -d mineru`。

### 13.5 实测结论与已知缺口

**实测（2026-09-18）**：

| 输入 | 解析器 | 结果 |
|---|---|---|
| `.txt` / `.md` | txt | 正常，1 块 |
| `.pdf`（两页含表格） | mineru | 2 页 / 2 块，块类型 `paragraph_title`/`text`/`table` 识别正确，表格保留 Markdown 结构，端到端约 3 秒 |
| `.docx`（含标题/表格/分页） | mineru | 正常结构化解析 |
| `.png`（含中文说明） | mineru | **图片 OCR 成功**，识别文字进入向量库 |
| `.pdf`（停掉 MinerU） | **pdfplumber（降级）** | 自动回退成功、`degraded=True`、上传未失败、降级原因入库 |

**第九阶段已完成的收口项**：

1. 上传已改为 `pending → processing → completed/degraded/failed`，由独立 worker 执行解析、分块、Embedding 与 Milvus 双写；
2. `degraded` 使用独立文档状态，降级原因仍写入 `parse_error` 便于排查；
3. 结构化块中的图片/表格/公式资产已保存为文档级 `manifest.json`，删除文档时一并清理；
4. 文件 SHA-256 + 解析器签名组成缓存键，缓存命中时只跳过解析，分块仍按当前配置重新计算；
5. MinerU 首次冷启动仍可能需要 warmup，但客户端已对首次连接拒绝/连接超时做指数退避，持久 worker 负责后续任务重试；
6. MinerU job 索引本身不作为持久队列，数据库 `document_tasks` 才是重启恢复和超时回收的事实来源。

---

## 14. 容器化部署与离线模型挂载（第七阶段）

### 14.1 部署拓扑与依赖门槛

`deploy/docker-compose.yml` 一条命令拉起六个服务：MySQL（元数据）、etcd + MinIO + Milvus standalone（向量库）、MinerU（解析）、Ollama（本地 LLM）、后端（FastAPI）。依赖用**健康检查**串起来，而不是只判 `service_started`：

| 服务 | 健康检查 | 为什么需要 |
|---|---|---|
| mysql | `mysqladmin ping` | ORM 建表依赖真实可连，否则后端启动即报连接失败 |
| etcd / minio | `etcdctl endpoint health` / MinIO health 接口 | Milvus 启动前必须就绪 |
| ollama | `ollama show qwen3:8b` | **模型能列出来才算就绪**，顺带验证宿主模型目录挂载正确（比 `service_started` 强很多） |
| backend | `/health` HTTP 探针 | 前端与调用方的可用性判定 |

### 14.2 模型来源：为什么用 bind mount，而不是 `ollama pull` / `COPY` 进镜像

| 方案 | 优点 | 代价 |
|---|---|---|
| 容器内 `ollama pull`（原方案） | 镜像最小 | 每次部署都要联网重下 4.9GB；客户内网/断网直接不可用 |
| 把权重 `COPY` 进自定义镜像 | 启动即用、镜像自包含 | 多 5GB 层、换模型要重建镜像；权重与代码强耦合 |
| **宿主目录 bind mount（本方案）** | 离线可用、模型与镜像解耦、换模型只换目录 | 依赖宿主目录约定；Windows bind mount 首次加载比镜像层慢 |

后端侧同一理由：`EMBEDDING_MODEL=/models/bge-m3`（容器内固定路径）+ 宿主 bge-m3 目录只读挂载，`sentence-transformers` 直接读本地目录，全链路不触发 HuggingFace 下载。

### 14.3 路径解析与配置边界（最容易踩的坑）

- `volumes` 的**相对路径以 compose 文件所在目录为基准**，不是执行命令时的 cwd：因此默认写 `../../models`、`../../bge-m3`（deploy → RAG-project → 工作区根）；
- compose 的**变量插值只读 `deploy/.env` 与 shell 环境变量**（工程目录 = compose 文件目录，工程名即 `deploy`）；`RAG-project/.env` 是应用配置、**不参与插值**——已实测：在其中写入变量不影响 `docker compose config` 的输出。职责分离：`.env` 管应用行为，`deploy/.env` 管编排参数；
- 模型换目录用 `OLLAMA_MODELS_HOST_PATH` / `EMBEDDING_MODEL_HOST_PATH` 覆盖，**建议写绝对路径**，避免相对基准再次出错。

### 14.4 读写边界

- Ollama：`/root/.ollama` 仍挂命名卷（密钥、历史等可写状态），只把 `/root/.ollama/models` 换成宿主目录 → 已有权重直接用，后续 `ollama pull` 新模型也仍然可写；
- bge-m3：`:ro` 只读。推理只读不写，只读挂载可避免容器污染宿主权重。

### 14.5 已知代价与显存竞争

- Embedding 容器内**走 GPU**（`EMBEDDING_DEVICE=cuda` + backend 服务预留 GPU 设备）：实测镜像内 torch 为 `2.14.0+cu130`，在 RTX 5080 Laptop（Blackwell，sm_120）上 `cuda.is_available()=True`——原先"镜像内是 CPU 版 torch、要用 GPU 必须换 torch 底座"的结论**已作废**；真正的瓶颈只是 compose 没给 backend 预留设备（没设备时 torch 自动落到 CPU，且 `BgeEmbeddingService` 会打 WARNING 回退、不报错，最容易被忽略）；
- 测量方法与结论（同机同镜像、预热后排除 CUDA 首次调用开销）：CPU 单条 447ms / 批量 512 条 15.9s，GPU 单条 12.8ms / 批量 512 条 1.42s，约 11~35 倍；线上容器预热后实测单次查询 `embedding_ms≈72ms`（此前 CPU 首次查询曾达 13.1s）。**"配置成 CPU 也能跑通"的降级路径最容易漏掉——能跑 ≠ 跑在对的设备上**：验证要直接问 torch（`torch.cuda.is_available()`）并看 `nvidia-smi` 进程，而不是看配置项写没写 cuda；
- Ollama、MinerU、backend **三个容器共用一张显卡**：Ollama 常驻 qwen3:8b（约 5.6GB）、bge-m3（约 2.2GB），MinerU 是 vLLM，启动 warmup（约 2~3 分钟）时一次性预占显存。显存不足时按代价让出：先让 Ollama 走 CPU（删 `deploy.resources` 段），再给 MinerU 降档，最后才把 Embedding 退回 CPU；
- 模型文件位于 Windows bind mount，mmap 读取性能不如镜像层，故设 `OLLAMA_KEEP_ALIVE=30m` 让模型常驻，用显存换掉"间隔稍长就重新加载 5.2GB"。

---

## 15. 前端架构与 UI/UX 重构（第十二阶段）

### 15.1 技术选型：从"无构建单页 HTML"到 Vue 3 + Element Plus

原前端是 `app/static/index.html` 单文件（原生 JS，约 480 行），三个 Tab 硬编码。UI/UX 设计方案（V1.0）要求 Sidebar 信息架构、Chunk 查看器、Pipeline 可视化、引用抽屉等组件体系，继续用原生 JS 堆会快速失控，因此按方案第 8 节升级为 Vue 3 + TypeScript + Vite + Element Plus + SCSS + Pinia + Axios。

**托管方式不变**：构建产物仍由 FastAPI `StaticFiles(html=True)` 同源托管在 `/`，不引入 Nginx/Node 运行时——客户本地部署形态零变化。

### 15.2 路由：为什么用 hash 模式

`StaticFiles(html=True)` 只把目录根的 `index.html` 映射到 `/`，**没有 history 模式的 404 回退**：SPA 若用 `createWebHistory()`，用户直接访问 `/#/chat` 之外的深链接（如刷新 `/documents`）会拿到 404。hash 路由（`createWebHashHistory()`）把路由状态放在 `#` 后，服务端只认 `/` 一个入口，零配置可用；代价是 URL 带 `#`，对内网工具可接受。若未来上 Nginx，加一条 `try_files ... /index.html` 即可切回 history 模式（路由表已按标准 path 定义，切换只改一行）。

### 15.3 构建与同步管线（Docker 不依赖 Node 的关键决策）

```
frontend/（源码，入库）
  └─ npm run build:static
       ├─ vite build          → frontend/dist（base './' 相对路径产物）
       └─ scripts/sync-static.mjs → 清空并覆盖 app/static/（构建产物随 git 提交）
```

| 决策 | 理由 |
|---|---|
| 产物提交进 git，Dockerfile **不加 Node 阶段** | 客户镜像构建环境不要求Node/npm 网络；`COPY app ./app` 直接带上前端 |
| `base: './'` | 产物不假设挂载前缀，`/` 或子路径都能跑 |
| sync 脚本先清空目标目录 | 旧单页 index.html 必须被替换掉，避免新旧入口并存误导 |
| `.gitignore` 忽略 `frontend/node_modules` 与 `frontend/dist` | 源码与最终产物入库，中间产物不入库 |

npm 依赖统一走 `registry.npmmirror.com`（frontend/.npmrc），与 Dockerfile pip 用清华源同一策略：国内直连、免代理、离线可用（装完即断网也能构建）。

### 15.4 Design Tokens 与 Element Plus 主题定制

- Tokens（方案 3.1~3.3）落地在 `frontend/src/styles/tokens.scss`：`--rag-*` CSS 变量（主色 #3370FF、浅灰底 #F5F6F7、白表面、细边框 #DEE0E3、四档间距、Sidebar 232px/Header 56px/内容宽 1360px）；
- EP 主题用**官方 SCSS `@forward ... with` 覆盖 `$colors`**（主色/成功/警告/危险对齐 Tokens），而不是散装 CSS 变量——一次性生成全部派生色阶（light-3/5/7/8/9、dark-2 等），hover/active 态自动成套；
- **踩坑：`$font-family` 不能用 `@forward` 覆盖**——EP 内部它是 map 结构（含各组件字体栈），传字符串会炸 `assertMap`。字体改为覆盖 CSS 变量 `--el-font-family` + body 基础样式，双保险；
- **离线红线**：不引在线字体/图标 CDN，字体栈 `Inter, "Noto Sans SC", "PingFang SC", "Microsoft YaHei"`（系统没有 Inter 时自动回退，视觉损失最小）。

### 15.5 页面与信息架构（P0 → P1/P2）

| 优先级 | 页面 | 后端依赖 |
|---|---|---|
| P0 ✅ | 布局骨架 + 知识库（表格模式） | 已有接口 |
| P0 ✅ | 文档（上传 + Pipeline 状态可视化 + 文档表） | 已有接口（status 轮询） |
| P0 ✅ | AI 助手（SSE 流式 + Markdown + 引用来源抽屉） | 已有 `/api/v1/chat` |
| P0 | 检索测试（Query → Retriever → 最终 Context） | **新增 `POST /api/v1/retrieval/test`（只检索不生成）** |
| P1 | Chunk 查看器（原文 ↔ Chunk ↔ Metadata） | 需新增按文档查 chunk 接口 |
| P1/P2 | 工作台 / 模型中心 / 监控 / 历史会话 | 部分需后端新增能力 |

**诚实边界**：当前检索是 dense-only 单路 ANN（无 BM25/hybrid/RRF/Rerank，见 PROJECT_PLAN 决策），检索测试页按真实能力展示 `Vector Search → 阈值过滤 → Top-K Context`，不做 hybrid/Rerank 假开关；设计方案中的这些能力标注为路线图。

### 15.6 前端侧踩坑记录

1. **npm 缓存目录沙箱/权限**：默认 cache 在 `D:\program_data\npm`（Agent 沙箱不可写）报 EPERM，且中断的安装会留下残缺 `node_modules`（二次安装报 `ENOTEMPTY: rmdir minimatch/dist/commonjs`）。解法：`npm install --cache <可写目录>`；清理残缺目录用 `node -e "fs.rmSync(path,{recursive:true,force:true,maxRetries:20})"`（PowerShell `Remove-Item` 对 node_modules 长路径/特殊文件会失败）；
2. **npm 11 的 install-scripts 审批机制**：`esbuild` 的 postinstall 被 `allow-scripts` 拦截不执行，直接 build 会因缺平台二进制失败。解法：手动 `node node_modules/esbuild/install.js` 补跑（`@parcel/watcher` 仅 dev watch 用，build 不需要）；
3. **EP 全量引入**：未做按需（unplugin-auto-import），主 chunk 约 1.06MB（gzip 349kB）。内网单机部署可接受；若后续要优化，加 unplugin 两个 devDep 即可，业务代码零改动。
4. **Pipeline 粒度诚实边界**：后端 `document_tasks` 只暴露文档级状态（0/1/2/3/4），`ProcessingPipeline.vue` 的 8 个节点里"解析→清洗→分块→向量化→入库"在 status=1 时**整体高亮**而非逐个点亮——前端不伪造细分进度；要精确到步骤需后端在任务表加 `current_step` 字段，属 P1 增强。
5. **vue-tsc 的跨函数属性窄化**：轮询函数内给 `ref` 赋值后，调用方读 `processing.value` 会被 CFA 窄化成非预期类型（踩到 `never`）。让轮询函数 `return` 终态值、调用方直接用返回值，不要读兄弟函数的 ref 副作用。

---

> 更新记录：v0.2 2026-08-21 覆盖第一、二阶段技术方案与面试要点；移除运维/环境层面的琐碎问题记录（本文档只沉淀有讲解价值的代码设计与面试要点）。
> v0.3 2026-08-27 新增第三阶段：Embedding 抽象、Milvus collection 设计、双写一致性落地、环境工程要点。
> v0.4 2026-08-28 新增第四阶段：知识库接口设计、删除级联顺序、批量删除不触发 ORM 级联、Milvus 删除异步语义。
> v0.5 2026-08-28 新增第五阶段：RAG 问答链路、SSE 协议、httpx 手动解析 SSE（含推理模型 reasoning_content 陷阱）、防幻觉双保险。
> v0.6 2026-09-17 新增第十二章：技术选型决策记录——自研编排 vs LangChain 的逐层对标、选型理由、取舍总览与混合演进路线。
> v0.7 2026-09-18 新增第十三章：本地 MinerU 接入（私有部署边界、V1 API 作业流、ParseResult 结构化扩展的兼容设计、端口/安全边界、实测结论与已知缺口）。
> v0.8 2026-09-18 第十三章补充：多格式分派（txt/md 原生、pdf 可切换、office/图片走 MinerU）、FallbackDocumentParser 降级设计与 except 变量作用域陷阱、MIME 按扩展名推断、五种格式实测结果。
> v0.9 2026-09-18 新增 2.4 同名文件冲突策略决策：由「一律拒绝」改为「显式覆盖」（`overwrite` 参数 + 前端确认），含四种策略对比、先写后删的顺序约束、doc_count 与审计影响。
> v1.0 2026-09-18 补充第六阶段稳定性保护、第十阶段 Ollama 原生流式协议，以及第九阶段异步 worker/缓存/assets 的收口结论。
> v1.1 2026-09-18 新增第十四章：容器化部署与离线模型挂载——服务依赖门槛（健康检查）、三种模型来源方案取舍、bind mount 相对路径基准与 compose 插值边界（`deploy/.env` vs 项目 `.env`）、读写边界、显存竞争与 CPU Embedding 的取舍。
> v1.2 2026-09-23 新增第十五章：前端架构与 UI/UX 重构——Vue 3 + Element Plus 选型、hash 路由约束、构建产物入库使 Docker 不含 Node 阶段、EP `@forward` 主题定制与 `$font-family` 陷阱、P0/P1 页面与诚实边界（dense-only）。
> v1.3 2026-09-23 15.5 进度更新（知识库/文档页已交付）、15.6 补记两条：Pipeline 任务级粒度诚实边界（不伪造细分步骤进度）、vue-tsc 跨函数属性窄化陷阱。
> v1.4 2026-09-23 15.5 进度更新（Chat 页已交付）；15.6 补记：SSE 客户端必须用原生 fetch+ReadableStream（axios 的 responseType:'stream' 在浏览器端不可用）、中断问答用 AbortController 且必须在 catch 里用 signal.aborted 区分"用户主动停止"与真实错误（前者保留部分回答、后者进错误气泡）。
