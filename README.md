# 企业知识库 RAG

这是一个可在本地或容器中运行的知识库应用。用户上传文档后，系统会解析内容并建立向量索引；提问时从文档中检索相关片段，再由大模型生成带来源的回答。

## 主要功能

- 管理知识库和文档，查看文档处理状态及分块内容。
- 解析文本、PDF、Office 文档和图片；部分格式需要 MinerU 服务。
- 使用本地 Embedding 模型和 Milvus 检索文档。
- 流式问答、查看回答来源，并单独测试检索结果。

后端使用 FastAPI，前端使用 Vue 3；MySQL 保存业务数据，Milvus 保存向量。大模型可配置为本地 Ollama 或 在线服务。

## 启动方式

### Docker 部署

准备好 Docker、所需镜像和本地模型后，在项目根目录运行。默认模型目录与项目并列放在项目根目录下：

```text
RAG-project/
├─ models/       # Ollama 模型仓库，包含 manifests/ 和 blobs/
├─ bge-m3/       # BAAI/bge-m3 本地权重目录
└─ deploy/
   └─ docker-compose.yml
```

Compose 会把 `models/` 挂载到 Ollama 容器的 `/root/.ollama/models`，把 `bge-m3/` 只读挂载到后端容器的 `/models/bge-m3`。如果模型已经放在其他位置，可在 `deploy/.env` 覆盖宿主机目录；具体格式见 [Docker 部署说明](DOCKER-README.md)。

然后在项目根目录运行：

```powershell
docker compose -f deploy/docker-compose.yml up -d --build
docker compose -f deploy/docker-compose.yml ps
```

Compose 使用本地镜像标签和本机模型文件，不会执行 `ollama pull`。首次部署前请按 [Docker 部署说明](DOCKER-README.md)准备。

### 本地开发

在 Python 环境中安装依赖，将 `.env.example` 复制为 `.env`，并填写数据库、Milvus、模型及大模型服务配置。依赖服务就绪后启动后端：

```powershell
pip install -r requirements.txt
uvicorn app.main:app --reload
```

前端源码在 `frontend/`。开发时进入该目录运行 `npm install`、`npm run dev`；准备部署时运行 `npm run build:static`，将页面更新到 `app/static/`。

启动后访问：

- 页面：<http://127.0.0.1:8000/>
- API 文档：<http://127.0.0.1:8000/docs>
- 健康检查：<http://127.0.0.1:8000/health>

## 目录说明

| 目录 | 内容 |
|---|---|
| `app/` | 后端代码和前端构建产物 |
| `frontend/` | 前端源码 |
| `deploy/` | Docker Compose 配置 |
| `docs/` | 技术设计说明 |
| `scripts/` | 数据检查与向量重建工具 |
| `sql/` | 数据库表结构 |

配置项可参考 `.env.example`，系统设计见 [技术设计](docs/TECH_DESIGN.md)。
