# Docker 部署

在项目根目录执行下列命令。Compose 会启动数据库、Milvus、MinerU、Ollama 和后端。

## 模型目录

默认把模型放在项目根目录，与源码目录并列：

```text
RAG-project/
├─ models/       # Ollama 模型仓库，包含 manifests/ 和 blobs/，例如 qwen3:8b
├─ bge-m3/       # BAAI/bge-m3 的 sentence-transformers 权重，向量维度为 1024
└─ deploy/
   └─ docker-compose.yml
```

Compose 文件中的宿主机路径相对 `deploy/` 解析，因此默认挂载关系是：

| 项目目录 | 容器目录 | 用途 |
|---|---|---|
| `../models` | `/root/.ollama/models` | Ollama 本地模型仓库 |
| `../bge-m3` | `/models/bge-m3`（只读） | 后端 Embedding 权重 |

目录名和模型内容需与配置匹配；默认 LLM 模型为 `qwen3:8b`，Embedding 维度为 1024。Docker 启动时直接使用这些本地文件，不会执行 `ollama pull` 或从 Hugging Face 下载模型。

默认目录就位时不需要 `deploy/.env`。如果模型目录在其他位置，先复制已提交的模板，再在 `deploy/.env` 中写宿主机绝对路径。Windows 路径建议使用正斜杠：

```powershell
Copy-Item deploy/.env.example deploy/.env
```

然后编辑 `deploy/.env`，填写实际路径：

```dotenv
OLLAMA_MODELS_HOST_PATH=D:/path/to/ollama-models
EMBEDDING_MODEL_HOST_PATH=D:/path/to/bge-m3
```

Compose 会继续把它们分别挂载到上表中的容器目录。`deploy/.env` 是本机配置文件，不要提交模型文件或真实机器路径到仓库。

## 构建

确认本机已有 `deploy/docker-compose.yml` 引用的第三方镜像，然后构建后端镜像：

```powershell
docker compose -f deploy/docker-compose.yml build backend
```

## 启动

```powershell
docker compose -f deploy/docker-compose.yml up -d
docker compose -f deploy/docker-compose.yml ps
```

启动后访问 <http://127.0.0.1:8000/>，API 文档在 <http://127.0.0.1:8000/docs>。

## 前端

前端页面由后端直接提供。只有修改了 `frontend/` 源码，才需要重新生成页面并构建后端：

```powershell
cd frontend
npm install
npm run build:static
cd ..
docker compose -f deploy/docker-compose.yml up -d --build backend
```
