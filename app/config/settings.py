"""全局配置模块。

设计要点：
1. 使用 pydantic-settings 从项目根目录的 .env 读取配置，杜绝硬编码；
2. .env 路径基于「本文件位置」上溯解析，而不是当前工作目录(cwd)，
   这样无论从哪个目录启动 uvicorn，都能找到同一个 .env；
3. get_settings() 用 lru_cache 缓存，进程内只解析一次 .env，后续全部复用；
4. 提供路径/字节等计算属性，业务层直接用语义化属性，不重复换算。
"""

from functools import lru_cache
from pathlib import Path
from typing import Set

from pydantic_settings import BaseSettings, SettingsConfigDict

# 项目根目录：本文件位于 app/config/settings.py，上溯 3 级
#  - parent1 = app/config
#  - parent2 = app
#  - parent3 = 项目根目录（RAG-project）
BASE_DIR = Path(__file__).resolve().parent.parent.parent


class Settings(BaseSettings):
    """全局配置模型，字段名即 .env 中的变量名（大小写不敏感）。"""

    model_config = SettingsConfigDict(
        # 指定 .env 的绝对路径，不依赖启动时的 cwd
        env_file=str(BASE_DIR / ".env"),
        env_file_encoding="utf-8",
        # 环境变量名与字段名匹配时大小写不敏感：APP_NAME -> app_name
        case_sensitive=False,
        # .env 中多余的变量（如后续阶段预留项）直接忽略，不报错
        extra="ignore",
    )

    # ---------- 应用 ----------
    app_name: str = "RAG Knowledge Base Service"
    app_version: str = "0.1.0"
    # 调试模式：true 时 FastAPI 返回详细错误（生产必须 false）
    debug: bool = False

    # ---------- 服务 ----------
    host: str = "0.0.0.0"
    port: int = 8000

    # ---------- 文件上传 ----------
    upload_dir: str = "uploads"
    max_upload_size_mb: int = 20
    # 允许的后缀名，逗号分隔字符串（.txt,.pdf）
    allowed_extensions: str = ".txt,.pdf"

    # ---------- 日志 ----------
    log_level: str = "INFO"
    log_dir: str = "logs"

    # ---------- 文本清洗（开关：false 时跳过对应规则） ----------
    clean_remove_invisible: bool = True   # 去除不可见乱码字符
    clean_collapse_newlines: bool = True  # 压缩连续换行（3+ → 2）
    clean_collapse_spaces: bool = True    # 压缩多余空白空格

    # ---------- 解析预览 ----------
    preview_max_chars: int = 200          # 清洗后文本预览片段最大长度

    # ---------- 文本分块 ----------
    chunk_size: int = 500                 # 分块大小（字符数）
    chunk_overlap: int = 50               # 相邻块重叠量（字符数）

    # ---------- MySQL ----------
    mysql_host: str = "127.0.0.1"
    mysql_port: int = 3306
    mysql_user: str = "root"
    mysql_password: str = ""
    mysql_db: str = "rag_knowledge"

    # ---------- 计算属性：业务层直接使用语义化值 ----------

    @property
    def upload_dir_path(self) -> Path:
        """上传目录绝对路径；配置相对路径时基于项目根目录解析。"""
        p = Path(self.upload_dir)
        return p if p.is_absolute() else BASE_DIR / p

    @property
    def log_dir_path(self) -> Path:
        """日志目录绝对路径；配置相对路径时基于项目根目录解析。"""
        p = Path(self.log_dir)
        return p if p.is_absolute() else BASE_DIR / p

    @property
    def max_upload_size_bytes(self) -> int:
        """单文件大小上限（字节），供上传校验使用。"""
        return self.max_upload_size_mb * 1024 * 1024

    @property
    def allowed_extension_set(self) -> Set[str]:
        """允许的后缀名集合（已小写化、去空格），供后缀名校验使用。"""
        return {e.strip().lower() for e in self.allowed_extensions.split(",") if e.strip()}

    # ---------- 生命周期 ----------

    def ensure_dirs(self) -> None:
        """启动时确保关键目录存在（上传目录、日志目录）。"""
        self.upload_dir_path.mkdir(parents=True, exist_ok=True)
        self.log_dir_path.mkdir(parents=True, exist_ok=True)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """获取全局配置单例。

    lru_cache 保证整个进程生命周期内 .env 只被解析一次，
    后续任何模块调用 get_settings() 拿到的都是同一份配置对象。
    """
    return Settings()
