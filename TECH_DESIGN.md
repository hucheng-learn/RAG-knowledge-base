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

### 5.4 边界处理（写代码时容易漏的）

- 空文本 → 空列表；
- `overlap < 0 或 >= chunk_size` → **抛业务异常**（窗口不前进会死循环）；
- 末尾不足块长 → 直接收尾；
- `start = max(end - overlap, start + 1)` 兜底保证窗口**至少前进 1 字符**。

---

## 6. MySQL 表设计（面试重点）

### 6.1 三张表结构与字段理由（DDL 见 `PROJECT_PLAN` 8.2 说明，此处为设计意图）

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

### 6.5 双写一致性（MySQL + Milvus，第三阶段落实）

- 入库：**先 MySQL 落库**（拿到 chunk_id）→ **再写 Milvus**（向量 id 与 chunk_id 一一对应）→ 任一步失败**补偿删除**；
- 删除：先删 Milvus 向量 → 再删 MySQL 记录（或软删 + 定时清理兜底）；
- **面试必答**："MySQL 有记录但 Milvus 没向量"→ 对账任务（定期比对两边 id，差异补偿）。

### 6.6 字段设计：为异步管线预留的状态字段（第四阶段对齐）

实际表比基础版多出一组「状态/配置」字段，反映最初设计里**异步管线**的意图：

| 字段 | 含义 | 设计意图 |
|---|---|---|
| `documents.status` (0待解析/1解析中/2完成/3失败) + `parse_error` | 解析状态 + 失败原因 | 支持异步解析（上传后后台处理，前端轮询状态） |
| `chunks.embedding_status` (0待嵌入/1已嵌入/2失败) | 向量化状态 | 单独跟踪每个 chunk 的嵌入进度，失败可精准重试 |
| `knowledge_bases.embedding_model / chunk_strategy / chunk_size / chunk_overlap` | 每库独立配置 | 不同知识库用不同模型/分块策略（覆盖全局默认） |
| `knowledge_bases.owner_id` | 归属用户 | 多租户/多用户隔离铺路 |
| `knowledge_bases.doc_count` | 冗余文档数 | 反规范化，列表免 COUNT join |

当前实现是**同步管线**（上传内完成解析+嵌入，成功即 status=2 / embedding_status=1），所以这些状态字段在成功路径上直接跳到终态；字段本身为将来改异步保留了扩展空间。`doc_count` 是唯一真正被用到的冗余列（上传自增、删除自减，list 直接读取，免 COUNT）。

---

## 7. 日志与可观测性

- **滚动文件**：RotatingFileHandler，10MB/个 × 5 个备份，防日志无限膨胀（生产日志必须滚动）；
- **文件格式带文件名行号** `(file.py:42)`，线上排查定位到行；
- **请求日志中间件**：每个请求记 `方法 路径 -> 状态码 (耗时ms)`，异常打完整堆栈；
- 日志级别、目录全部 .env 可配。

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

- **GPU 推理**：`EMBEDDING_DEVICE=cuda`，查询向量化 0.37s（RTX 5080），CPU 会慢一个数量级；
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

---

> 更新记录：v0.2 2026-08-21 覆盖第一、二阶段技术方案与面试要点；移除运维/环境层面的琐碎问题记录（本文档只沉淀有讲解价值的代码设计与面试要点）。
> v0.3 2026-08-27 新增第三阶段：Embedding 抽象、Milvus collection 设计、双写一致性落地、环境工程要点。
> v0.4 2026-08-28 新增第四阶段：知识库接口设计、删除级联顺序、批量删除不触发 ORM 级联、Milvus 删除异步语义。
> v0.5 2026-08-28 新增第五阶段：RAG 问答链路、SSE 协议、httpx 手动解析 SSE（含推理模型 reasoning_content 陷阱）、防幻觉双保险。
