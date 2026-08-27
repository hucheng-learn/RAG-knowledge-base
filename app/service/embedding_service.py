"""Embedding 抽象接口 + bge-m3 本地实现（sentence-transformers）。

设计（面试点）：
1. EmbeddingService 抽象：embed_texts / embed_query / dim —— 换模型
   （bge-large、远端 API）只换实现，不动上层业务；
2. embed_query 单独抽象：旧版 bge-large/small 查询需加指令前缀
   "为这个句子生成表示以用于检索相关文章"，bge-m3 不需要，
   不同模型可各自实现，保证查询与文档向量空间一致；
3. normalize_embeddings=True（归一化）+ Milvus 的 COSINE 度量匹配，
   归一化后点积等价余弦，检索更稳；
4. lru_cache 单例：模型权重 ~2.2GB、加载数秒，进程内只加载一次；
5. 懒加载：模型在首次调用时才创建，import 不触发（避免启动变慢、
   且 HF 下载问题不影响服务启动）。
"""

import os
from abc import ABC, abstractmethod
from functools import lru_cache

from app.config.settings import get_settings
from app.utils.exceptions import SystemException
from app.utils.logger import get_logger

logger = get_logger(__name__)


class EmbeddingService(ABC):
    """向量化抽象接口。"""

    @property
    @abstractmethod
    def dim(self) -> int:
        """向量维度。"""

    @abstractmethod
    def embed_texts(self, texts: list) -> list:
        """批量文本向量化（用于文档块）。"""

    @abstractmethod
    def embed_query(self, query: str) -> list:
        """单条查询向量化（用于用户提问）。"""


class BgeEmbeddingService(EmbeddingService):
    """基于 sentence-transformers 的 bge-m3 本地实现。"""

    def __init__(self) -> None:
        # 延迟 import：sentence_transformers + torch 体积大、加载慢，
        # 只有真正创建服务时才引入，避免拖慢应用启动
        import torch
        from sentence_transformers import SentenceTransformer

        settings = get_settings()

        # HF_ENDPOINT 仅在「联网下载仓库名模型」时生效；本地路径加载不触发
        # 下载，这行为「切换到 BAAI/bge-m3 等仓库名」时的镜像兜底，可 .env 覆盖。
        os.environ.setdefault("HF_ENDPOINT", settings.hf_endpoint)

        # 设备兜底：配置要求 cuda 但 torch 非 GPU 版 / 驱动异常时回退 cpu，
        # 避免首次调用（懒加载）才抛 RuntimeError、错误信息难定位。
        device = settings.embedding_device
        if device == "cuda" and not torch.cuda.is_available():
            logger.warning("cuda 不可用（torch 非 GPU 版或驱动异常），回退到 cpu")
            device = "cpu"

        logger.info("加载 embedding 模型: %s device=%s", settings.embedding_model, device)
        self._model = SentenceTransformer(settings.embedding_model, device=device)
        # ST 6.0 将 get_sentence_embedding_dimension 改名为 get_embedding_dimension，getattr 兼容新旧
        getter = getattr(self._model, "get_embedding_dimension", None)
        if getter is None:
            getter = self._model.get_sentence_embedding_dimension
        self._dim = getter()

        # 维度校验：Milvus collection 按 settings.embedding_dim 建，向量按模型
        # 实际维度产；两者不一致时入库会报 dimension mismatch，这里提前失败、
        # 报错更清晰（换模型时最易踩）。
        if self._dim != settings.embedding_dim:
            raise SystemException(
                f"embedding 维度不一致: 模型实际={self._dim}, 配置={settings.embedding_dim}"
            )
        logger.info("embedding 模型就绪: dim=%d", self._dim)

    @property
    def dim(self) -> int:
        return self._dim

    def embed_texts(self, texts: list) -> list:
        """批量向量化并归一化（match Milvus COSINE）。"""
        vecs = self._model.encode(texts, normalize_embeddings=True, show_progress_bar=False)
        return vecs.tolist()

    def embed_query(self, query: str) -> list:
        """查询向量化（bge-m3 无需指令前缀；bge-large/small 旧版需加前缀）。"""
        vec = self._model.encode(query, normalize_embeddings=True, show_progress_bar=False)
        return vec.tolist()


@lru_cache(maxsize=1)
def get_embedding_service() -> EmbeddingService:
    """获取全局单例（模型只加载一次）。"""
    return BgeEmbeddingService()
