# MinerU 4.0 本地部署

本目录用于客户本地部署 MinerU 4.0 V1 API。PDF 通过本机服务处理，不调用 MinerU 公有云 API。

## 前置条件

- Docker Desktop 已启用 Linux containers 和 WSL2
- NVIDIA 驱动及 NVIDIA Container Toolkit 可用
- 推荐至少 16GB 系统内存；本项目验证机使用 NVIDIA GPU
- 首次构建需要下载镜像和模型，模型文件应保存在本机受控目录

## 方式一：项目自用 compose（推荐，端口已避开冲突）

```powershell
# 1) 构建镜像（在 MinerU 官方仓库根目录执行，国内用 china 版 Dockerfile）
docker build -t mineru:4 -f docker/china/Dockerfile .

# 2) 启动服务（在 RAG 项目根目录执行）
docker compose -f deploy/docker-compose.mineru.yml up -d
curl.exe http://127.0.0.1:8001/v1/health
```

`deploy/docker-compose.mineru.yml` 要点：
- 宿主端口 **8001** → 容器 8000：本项目 FastAPI 占用 8000，避免冲突，且与 `.env` 的 `MINERU_API_URL` 一致；
- 端口只绑 `127.0.0.1`（回环），不暴露到局域网；
- 预留 NVIDIA GPU（`device_ids: ["0"]`）、`ipc: host`、放宽 memlock；
- `MINERU_MODEL_SOURCE=local`：使用镜像内模型，运行时不联网。

> ⚠️ 容器启动后**第一次**解析要等 vLLM 引擎 warmup（约 2~3 分钟），期间客户端可能遇到连接被拒；之后单篇解析约 3 秒。

## 应用侧配置（.env）

```ini
PDF_PARSER=mineru                              # pdfplumber（默认）或 mineru
MINERU_API_URL=http://127.0.0.1:8001           # 服务根地址，不含 /v1
MINERU_TIER=standard
MINERU_TIMEOUT_SECONDS=300
MINERU_MAX_POLLS=100
MINERU_POLL_INTERVAL_SECONDS=3
```

本地 MinerU 服务默认无鉴权，不配置 API Key。

已验证能力（2026-09-18）：两页中文 PDF → 2 页、6 个结构化块，块类型识别正确（`paragraph_title` / `text` / `table`），表格以 Markdown 结构完整保留，端到端约 3 秒。

## 方式二：MinerU 官方配置

从 MinerU 官方仓库获取对应版本的 `docker/` 目录后，在仓库根目录执行：

```powershell
docker build -t mineru:4.0.0 -f docker/global/Dockerfile .
docker compose -f docker/compose.yaml --profile api up -d
```

服务健康检查：

```powershell
curl.exe http://127.0.0.1:8000/v1/health
```

固定镜像版本并核对实际安装版本，不要只依赖 `mineru:4` 标签。应用侧使用 `http://127.0.0.1:8000` 作为服务根地址；MinerU 4.0 API 使用 `/v1` 上传、创建任务、轮询和下载结果，旧版 `/file_parse`、`/tasks` 路由不适用。

## 安全边界

- API 只绑定 `127.0.0.1`，不直接暴露到局域网；
- 若必须跨容器访问，使用内部 Docker 网络，并配置 `--api-key` 或认证反向代理；
- 应用的 `uploads/` 仅通过应用读取，不挂载为公网静态目录；
- MinerU 的临时上传目录与任务索引不是持久任务队列，容器重启后不能依赖旧 job id 恢复；持久化任务与重试由项目第九阶段实现。
