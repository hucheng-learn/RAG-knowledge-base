# 系统架构与关键设计

## 架构

项目采用前后端同源部署。FastAPI 提供 REST API 和 SSE 问答接口，并托管 Vue 前端构建产物。

| 部分 | 职责 |
|---|---|
| `app/routers/` | HTTP 参数校验、调用业务服务、组织响应 |
| `app/service/` | 文档处理、解析、分块、Embedding、检索和问答编排 |
| `app/models/` | API schema 与 SQLAlchemy ORM |
| `app/config/` | 从环境变量和 `.env` 读取配置 |
| MySQL | 知识库、文档、分块、处理任务和解析缓存元数据 |
| Milvus | 分块向量及检索所需的标识字段 |
| `frontend/` | Vue 单页应用源码；构建产物同步至 `app/static/` |

## 文档入库

上传接口先保存原文件、创建文档和处理任务并立即返回。后台 worker 领取任务，依次执行解析、文本清理、分块、Embedding 和向量写入；前端通过文档状态接口查看进度。

解析器按格式和配置选择：TXT/Markdown 使用内置解析器，PDF 使用 pdfplumber 或 MinerU，Office 与图片由本地 MinerU 处理。MinerU 出错或未提取到文本时，PDF 会回退到 pdfplumber。解析结果保留页码和可选的结构块信息，供分块与来源追溯使用。

文档任务以文档 ID 唯一关联，记录状态、尝试次数、下次执行时间和错误信息。任务处理在重试前清理该文档已有向量，并在写入前确保 Milvus collection 存在，以便重复执行和服务重启后恢复。解析缓存以文件内容摘要和解析配置确定；缓存解析结果，分块仍按当前配置生成。

## 分块与存储

分块记录保存在 MySQL，包括正文、顺序、页码、结构类型、标题路径和向量状态。Embedding 使用本地 bge-m3，默认向量维度为 1024。Milvus 保存向量及文档/分块标识；检索命中后以标识回查 MySQL，取得正文和展示信息。

MySQL 与 Milvus 不共享事务。写入或删除流程通过幂等操作和失败补偿减少不一致：可按文档清除向量并从 MySQL 分块重建，`scripts/rebuild_vectors.py` 提供重建/对账入口。表结构定义见 `sql/schema.sql`，应用启动时也会依据 ORM 创建缺失表。

## 检索与问答

问答流程将问题编码为向量，在知识库范围内进行 Milvus 相似度检索，再按相似度阈值和 Top-K 组织上下文。命中的分块和文档信息作为来源随回答返回。当前检索是 dense 向量检索，没有 BM25 混合检索或 reranker。

问答接口使用 SSE：`start` 发送来源，`delta` 发送回答片段，`done` 发送结束状态。前端用 `fetch` 和 `ReadableStream` 消费事件，支持中断生成。检索测试复用召回链路但不调用 LLM，便于独立查看命中内容、相似度与耗时。

## 删除与覆盖

删除文档时清理其处理任务、MySQL 分块、Milvus 向量、原始上传文件及关联解析资产；删除知识库时对其文档执行级联清理。同名文档覆盖采用显式参数：先处理新文档，成功后再清理旧文档，避免新版本处理失败时丢失旧数据。

## 前端与部署

前端使用 hash 路由，构建后由 FastAPI 静态托管，因此后端镜像无需 Node 构建阶段。`npm run build:static` 会同步产物到 `app/static/`，修改前端后应重新生成并提交对应产物。

Docker Compose 可部署 MySQL、Milvus、MinerU、Ollama 和后端。Compose 插值配置放在 `deploy/.env` 或 shell 环境；应用配置由项目根目录的 `.env` 提供。模型权重通过宿主目录挂载。MinIO 使用 `deploy_minio_data` 命名卷挂到镜像声明的 `/data` 路径，避免自动创建随机匿名卷。具体命令、端口和服务启停方式见 `deploy/README.md`。
