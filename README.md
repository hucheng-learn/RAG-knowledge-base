# 企业知识库 RAG 后端系统

基于 FastAPI + Milvus + MySQL 的企业知识库 RAG 后端，配套极简前端页面。

> 开发计划与进度跟踪见仓库根目录 `PROJECT_PLAN.md`。

## 当前进度

- 第一阶段：项目骨架 + 文件上传解析模块（已完成）
- 第二阶段：文本分块 + MySQL 元数据存储（已完成）
- 第三阶段：Embedding 接入 + Milvus 向量入库（已完成）

## 本地启动

```bash
# 1. 激活虚拟环境（本项目使用 conda 环境 rag_kb，已装 GPU torch）
conda activate rag_kb

# 2. 安装依赖（sentence-transformers 默认拉 CPU torch，需 GPU 请先自装对应
#    CUDA 版 torch，再执行本命令，详见 requirements.txt 说明）
pip install -r requirements.txt

# 3. 复制环境变量模板，并修改 EMBEDDING_MODEL（本地 bge-m3 路径）、
#    EMBEDDING_DEVICE（cuda/cpu）
copy .env.example .env          # Windows
# cp .env.example .env          # Linux/macOS

# 4. 启动 Milvus（依赖 Docker）
docker compose -f deploy/docker-compose.milvus.yml up -d

# 5. 启动服务
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

启动后访问：

- 健康检查：http://127.0.0.1:8000/health
- Swagger 文档：http://127.0.0.1:8000/docs

## 目录结构

见 `PROJECT_PLAN.md` 第 5 节（随阶段逐步落地）。
