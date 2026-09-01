# 企业知识库 RAG 后端系统

基于 FastAPI + Milvus + MySQL 的企业知识库 RAG 后端，配套极简前端页面。

> 开发计划与进度跟踪见仓库根目录 `PROJECT_PLAN.md`（唯一事实来源）。

## 当前进度

- 第一阶段：项目骨架 + 文件上传解析模块（已完成）
- 第二阶段：文本分块 + MySQL 元数据存储（已完成）
- 第三阶段：Embedding 接入 + Milvus 向量入库（已完成）
- 第四阶段：知识库管理接口 + 文档删除级联（已完成）
- 第五阶段：RAG 问答接口（SSE 流式 + 溯源）（已完成）
- 前端：极简单页 —— 待开发

## 本地启动

```bash
# 1. 激活虚拟环境（本项目使用 conda 环境 rag_kb，已装 GPU torch）
conda activate rag_kb

# 2. 安装依赖
pip install -r requirements.txt

# 3. 复制环境变量模板，并修改 EMBEDDING_MODEL（本地 bge-m3 路径）、
#    EMBEDDING_DEVICE（cuda/cpu）、MYSQL_PASSWORD
copy .env.example .env          # Windows
# cp .env.example .env          # Linux/macOS

# 4. 启动依赖服务
#    - MySQL：本机 MySQL80（需先运行）
#    - Milvus：依赖 Docker
docker compose -f deploy/docker-compose.milvus.yml up -d

# 5. 启动服务
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

启动后访问：

- 健康检查：http://127.0.0.1:8000/health
- Swagger 文档：http://127.0.0.1:8000/docs

## 已提供接口

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/v1/documents/upload?kb_id=` | 上传文档（txt/pdf ≤20MB），同步解析/分块/向量入库 |
| DELETE | `/api/v1/documents/{file_id}` | 删除文档（级联清理 Milvus/MySQL/文件） |
| POST | `/api/v1/kbs` | 新建知识库 |
| GET | `/api/v1/kbs` / `/api/v1/kbs/{id}` | 知识库列表 / 详情 |
| DELETE | `/api/v1/kbs/{id}` | 删除知识库（级联清理全部文档） |
| POST | `/api/v1/chat` | RAG 问答（SSE 流式：start 溯源 / delta 回答 / done 结束） |

## 目录结构

见 `PROJECT_PLAN.md` 第 5 节（随阶段逐步落地）。

## 前端

配套一个极简单页（知识库管理 / 文档上传 / RAG 问答），设计见 `PROJECT_PLAN.md` 第 11 节，待第五阶段完成后开发。

## 环境注意

- 国内网络：模型走 `hf-mirror.com` 直连；GitHub / Docker 拉取需本地代理；
- 本机 GPU（RTX 5080）用 `EMBEDDING_DEVICE=cuda`，无独显改 `cpu`。
