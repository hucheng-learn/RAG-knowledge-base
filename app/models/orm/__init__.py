"""SQLAlchemy ORM 初始化：引擎、会话工厂、建库建表。

设计要点（面试重点）：
1. 引擎参数：pool_size 连接池大小 + max_overflow 峰值扩容、
   pool_pre_ping 每次取连接前探活（防 MySQL 断连后拿到死连接）、
   pool_recycle 定时回收（MySQL wait_timeout 默认 8h，连接空闲超时
   会被服务端断开，必须提前回收重建）；
2. init_db()：先连「服务器」（不带库名）建库（utf8mb4 字符集），
   再连库建表。开发阶段用 create_all 自动建表；
   生产建议引入 Alembic 做版本化迁移（第七阶段可补）；
3. 表模型在文件底部导入，注册进 Base.metadata —— create_all 才能
   知道要建哪些表（SQLAlchemy 不会自动发现模型）。
"""

from typing import Optional

from sqlalchemy import create_engine, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config.settings import get_settings
from app.utils.logger import get_logger

logger = get_logger(__name__)

# 连接池参数
_POOL_SIZE = 5
_MAX_OVERFLOW = 10
_POOL_RECYCLE_SECONDS = 3600  # 1 小时回收一次


class Base(DeclarativeBase):
    """所有 ORM 模型的公共基类（SQLAlchemy 2.x 风格）。"""


# ---------------- 引擎与会话（惰性单例） ----------------

_engine = None
_session_factory: Optional[sessionmaker] = None


def _build_url(settings, database: Optional[str] = None) -> str:
    """构造 SQLAlchemy URL。

    database=None 时**不带库名**（仅连接 MySQL 服务器，
    用于先建库再连库的两步初始化）；否则连接指定库。
    charset=utf8mb4 保证中文与 emoji 存储正常。
    """
    base = f"mysql+pymysql://{settings.mysql_user}:{settings.mysql_password}" \
           f"@{settings.mysql_host}:{settings.mysql_port}"
    if database is None:
        # 注意：不能用 database or settings.mysql_db —— None 是合法语义
        # （连服务器），不能回退成默认库名，否则建库那步会连不存在的库
        return f"{base}/?charset=utf8mb4"
    return f"{base}/{database}?charset=utf8mb4"


def get_engine():
    """获取全局引擎（惰性创建，进程内单例）。"""
    global _engine
    if _engine is None:
        settings = get_settings()
        _engine = create_engine(
            # 必须显式传库名：database=None 是「只连服务器」的语义，
            # 不传会导致引擎没有默认库，SQL 报 1046 No database selected
            _build_url(settings, database=settings.mysql_db),
            pool_size=_POOL_SIZE,
            max_overflow=_MAX_OVERFLOW,
            pool_pre_ping=True,
            pool_recycle=_POOL_RECYCLE_SECONDS,
        )
    return _engine


def get_session():
    """获取一个数据库会话（每次调用新建，用完必须 close）。

    会话不是线程安全的，FastAPI 每个请求/线程各拿各的；
    推荐配合 with 或 finally 关闭（见 document_service 用法）。
    """
    global _session_factory
    if _session_factory is None:
        _session_factory = sessionmaker(
            bind=get_engine(), autoflush=False, expire_on_commit=False,
        )
    return _session_factory()


def init_db() -> None:
    """初始化数据库：确保库存在 + 建表（幂等，可重复调用）。"""
    settings = get_settings()

    # 第一步：连服务器建库（utf8mb4 + 通用排序规则）
    server_engine = create_engine(_build_url(settings, database=None), pool_pre_ping=True)
    try:
        with server_engine.connect() as conn:
            conn.execute(
                text(
                    f"CREATE DATABASE IF NOT EXISTS `{settings.mysql_db}` "
                    "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
                )
            )
            conn.commit()
    finally:
        server_engine.dispose()

    # 第二步：连库建表
    Base.metadata.create_all(bind=get_engine())
    logger.info(
        "MySQL 初始化完成: %s@%s:%s/%s",
        settings.mysql_user, settings.mysql_host, settings.mysql_port, settings.mysql_db,
    )


# ---------------- 模型注册（必须最后导入） ----------------

from app.models.orm import chunk, document, knowledge_base  # noqa: E402,F401
