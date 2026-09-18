# 全栈容器部署

`docker-compose.yml` 会启动 MySQL、Milvus、MinerU、Ollama 和后端。第十一阶段对照实验不包含在本部署流程内。

## 前置条件

- Docker Desktop 已启动，GPU 机器安装 NVIDIA Container Toolkit；
- 本地已有 `mineru:4` 镜像；
- 将本地 `bge-m3` 权重放到 `models/bge-m3`，或通过 `EMBEDDING_MODEL_HOST_PATH` 指定目录；
- Ollama 模型下载需要联网，默认使用 `qwen3:8b`。

## 启动

```powershell
docker compose -f deploy/docker-compose.yml up -d --build
docker compose -f deploy/docker-compose.yml exec ollama ollama pull qwen3:8b
docker compose -f deploy/docker-compose.yml ps
```

后端地址：`http://127.0.0.1:8000`。MinerU 首次启动需要等待模型 warmup。

## 停止

```powershell
docker compose -f deploy/docker-compose.yml down
```

默认 MySQL 宿主端口是 `3307`，避免与本机 MySQL80 的 `3306` 冲突；Milvus、MinerU 和 Ollama 使用现有开发端口。若端口被占用，可在项目 `.env` 中设置 `*_HOST_PORT` 覆盖。
