# 企业知识库 RAG 后端系统

基于 FastAPI + Milvus + MySQL 的企业知识库 RAG 后端，配套极简前端页面。

> 开发计划与进度跟踪见仓库根目录 `PROJECT_PLAN.md`（唯一事实来源）。

## 当前进度

- 第一阶段：项目骨架 + 文件上传解析模块（进行中）

## 本地启动

```bash
# 1. 创建虚拟环境并安装依赖
python -m venv .venv
.venv\Scripts\activate          # Windows
pip install -r requirements.txt

# 2. 复制环境变量模板
copy .env.example .env          # Windows
# cp .env.example .env          # Linux/macOS

# 3. 启动服务
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

启动后访问：

- 健康检查：http://127.0.0.1:8000/health
- Swagger 文档：http://127.0.0.1:8000/docs

## 目录结构

见 `PROJECT_PLAN.md` 第 5 节（随阶段逐步落地）。
