# AGENTS.md — 协作约定（所有 AI Agent 必读）

> 唯一事实来源：`docs/PROJECT_PLAN.md`——动手前先读，改完必须回写。技术方案见 `docs/TECH_DESIGN.md`。

## 1. 提交与文档（硬性）

- **小步提交**：改动不要攒，做完一小块立即 commit 到 `dev`（本地）；**只提交 `dev`**，`dev → main` 与推送远程由项目所有者执行；
- **改完必回写文档**（禁止"改代码不更文档"）：

| 改动 | 同步更新 |
|---|---|
| 任何改动 | `docs/PROJECT_PLAN.md`：版本号 + 最近更新日期 + 对应章节 + 变更记录追加一行 |
| 设计 / 取舍 / 原理 | `docs/TECH_DESIGN.md` |
| 数据库表结构 | `sql/schema.sql`，并跑 `python scripts/verify_schema.py` |
| 配置项增删改 | `.env` 与 `.env.example`（模板不得含真实密钥） |
| 进度 / 启动步骤 / 接口表 / 目录 / 依赖 / 开关说明 | `README.md` |
| 部署方式 | `deploy/` 下对应说明 |

## 2. 下载 / 网络

- **下载前先明确告知是否需要代理**；
- 需代理：GitHub、docker.io、官方 PyPI、HuggingFace；
- 直连更快：清华 PyPI、DaoCloud、ModelScope、hf-mirror（**阿里源实测 ~90kB/s 且断流，禁用**）；
- Dockerfile 内 pip 用清华源 + `--mount=type=cache,target=/root/.cache/pip`；大文件/模型优先让用户下载；
- 成功与否看**实际产物**（如 `docker images`），不看 PowerShell 退出码（Docker 进度写 stderr 会被误判）。

## 3. 环境

| 组件 | 命令 / 说明 |
|---|---|
| Python | conda 环境 `rag_kb`（GPU torch；`.venv` 已弃用） |
| MySQL | 本机 MySQL80（常驻） |
| Milvus | `docker compose -f deploy/docker-compose.milvus.yml up -d` |
| MinerU | `docker compose -f deploy/docker-compose.mineru.yml up -d`（`127.0.0.1:8001`） |
| 后端 | `conda activate rag_kb` → `uvicorn app.main:app --reload` |

## 4. 开发

按 `docs/PROJECT_PLAN.md` 阶段推进，**禁止一次性生成全部代码**；接口参数 Pydantic 强校验；日志记接口入参 / 文件名 / 异常堆栈；判断以实际产物与日志为准，不靠主观假设。
