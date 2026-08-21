"""全局日志工具。

设计要点：
1. setup_logging()：应用启动时调用一次，为根 logger 挂两个 handler：
   - 控制台 StreamHandler：开发时直接可见；
   - RotatingFileHandler 滚动文件：单文件 10MB、保留 5 个备份，防止日志无限膨胀。
2. get_logger(name)：业务模块用 `get_logger(__name__)` 获取 logger，
   自动继承根 logger 的 handler（logging 的父子传播机制），无需重复配置。
3. 日志级别从 .env 的 LOG_LEVEL 读取；日志目录从 LOG_DIR 读取。
"""

import logging
import sys
from logging.handlers import RotatingFileHandler
from typing import Optional

from app.config.settings import get_settings

# 模块级标志：防止 setup_logging() 被重复调用导致 handler 重复挂载
_configured: bool = False

# 控制台用简洁格式；文件用带文件名行号的详细格式（便于排查线上问题）
_CONSOLE_FORMAT = "%(asctime)s [%(levelname)s] %(name)s - %(message)s"
_FILE_FORMAT = "%(asctime)s [%(levelname)s] %(name)s (%(filename)s:%(lineno)d) - %(message)s"

# 日志滚动参数
_MAX_BYTES = 10 * 1024 * 1024   # 单文件 10MB
_BACKUP_COUNT = 5               # 保留 5 个历史文件


def setup_logging() -> None:
    """初始化全局日志（控制台 + 滚动文件）。幂等：重复调用直接返回。"""
    global _configured
    if _configured:
        return
    _configured = True

    settings = get_settings()

    # 确保日志目录存在（文件 handler 打开文件前必须存在目录）
    settings.log_dir_path.mkdir(parents=True, exist_ok=True)

    root = logging.getLogger()
    # .env 中配置的级别名转成 logging 级别常量，非法值兜底为 INFO
    level = getattr(logging, settings.log_level.upper(), logging.INFO)
    root.setLevel(level)

    # 控制台输出（开发环境可见）
    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(logging.Formatter(_CONSOLE_FORMAT))
    root.addHandler(console)

    # 滚动文件输出（生产排查用）
    file_handler = RotatingFileHandler(
        settings.log_dir_path / "app.log",
        maxBytes=_MAX_BYTES,
        backupCount=_BACKUP_COUNT,
        encoding="utf-8",
    )
    file_handler.setFormatter(logging.Formatter(_FILE_FORMAT))
    root.addHandler(file_handler)


def get_logger(name: Optional[str] = None) -> logging.Logger:
    """获取 logger 实例。

    Args:
        name: 模块名，约定传 __name__，日志里会带上 app.utils.xxx 前缀方便溯源。
    """
    return logging.getLogger(name)
