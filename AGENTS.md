# AGENTS.md — 协作约定（所有 AI Agent 与协作者必读）

> **唯一事实来源：`docs/PROJECT_PLAN.md`。** 开始任何工作前先读它；任何改动完成后必须回写文档。
> 技术方案与面试要点见 `docs/TECH_DESIGN.md`。

## 1. 文档同步（强制，最高优先级）

任何改动都必须同步更新对应文档，**禁止"改代码不更文档"**：

| 改动类型 | 必须同步更新 |
|---|---|
| 任何改动 | `docs/PROJECT_PLAN.md`：头部版本号 + 最近更新日期 + 对应章节 + 变更记录追加一行 |
| 设计决策 / 方案取舍 / 原理 | `docs/TECH_DESIGN.md` |
| 数据库表结构 | `sql/schema.sql`，并跑 `python scripts/verify_schema.py` 校验 ORM ↔ 实际库一致 |
| 配置项增删改 | `.env` 与 `.env.example` **同步**（模板中不得出现真实密钥） |
| **每次改动都要过一遍 README 必检项** | `README.md`：当前进度、启动步骤、已提供接口表、目录结构、依赖与环境要求、解析器/服务开关说明 |
| 部署方式 | `deploy/` 下对应 compose/说明文件 |

一次改动涉及多处文档时，**一并更新**。README 是外部读者第一入口，**不允许滞后**。

## 2. 分支约定

- 只提交到 **`dev`** 分支；
- `dev → main` 的合并、以及推送远程，**由项目所有者执行**，Agent 不做。

## 3. 下载 / 网络约定

- **任何下载动作前，先明确告知用户"是否需要开代理"**，再执行；
- **需要代理**：GitHub、docker.io 官方仓库、官方 PyPI、HuggingFace 本体；
- **不需要代理（直连更快，开代理反而可能拖慢/干扰）**：DaoCloud 镜像站、清华 PyPI（`pypi.tuna.tsinghua.edu.cn`）、ModelScope、`hf-mirror.com`；
  ⚠️ 阿里 `mirrors.aliyun.com` 实测本机极慢（~90kB/s）且频繁断流，**不要用于构建**；
- Dockerfile 内的下载**不走宿主机代理设置**：构建里的 pip 统一用清华源，并加 `--mount=type=cache,target=/root/.cache/pip` 缓存挂载；
- 大文件 / 模型下载优先让用户执行，用户处理不了时 Agent 再接管；
- **判断下载是否成功看实际产物**（如 `docker images`），不要看 PowerShell 退出码——Docker 进度写 stderr 会被误判为失败。

## 4. 环境约定

| 组件 | 说明 |
|---|---|
| Python 环境 | conda 环境 **`rag_kb`**（含 GPU torch；`.venv` 是旧的 CPU 环境，已弃用） |
| GPU | NVIDIA RTX 5080 Laptop（16GB），Embedding 走 `cuda` |
| MySQL | 本机 MySQL80（常驻服务） |
| Milvus | `docker compose -f deploy/docker-compose.milvus.yml up -d`（需先开 Docker Desktop） |
| MinerU | `docker compose -f deploy/docker-compose.mineru.yml up -d`，服务在 `127.0.0.1:8001` |
| 启动后端 | `conda activate rag_kb` → `uvicorn app.main:app --reload`（默认 127.0.0.1:8000） |

## 5. 开发约定

1. 严格按 `docs/PROJECT_PLAN.md` 的阶段推进，**禁止一次性生成全部代码**；每块代码附核心逻辑讲解；
2. 工业级标准：边界情况、异常捕获、参数校验，拒绝玩具 demo；
3. 所有接口参数用 **Pydantic 强校验**；接口签名改动要同步接口文档；
4. 日志打印关键信息：接口入参、文件名、异常堆栈；
5. 关键操作（构建、启动、健康检查）以**实际产物/日志**为准做判断，不靠退出码或主观假设。
