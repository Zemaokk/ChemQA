import math
from typing import Any

from config.settings import settings
from src.knowledge_base.vector_store import VectorStore
from src.qa_system.context import serialize_context
from src.utils.logger import logger


class Retriever:
    def __init__(self, *, retrieval_profile=None, reranker_profile=None):
        """初始化检索器"""
        try:
            if retrieval_profile is not None and reranker_profile is not None:
                raise ValueError("Choose one explicit raw retrieval profile")
            self.vector_store = VectorStore()
            if reranker_profile is not None:
                from src.knowledge_base.reranked_search import RerankedSearch

                self.raw_search = RerankedSearch.from_profile(
                    self.vector_store, reranker_profile
                )
            elif retrieval_profile is not None:
                from src.knowledge_base.hybrid_search import HybridSearch

                self.raw_search = HybridSearch.from_profile(
                    self.vector_store, retrieval_profile
                )
            logger.info("Retriever initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize Retriever: {e!s}")
            raise

    def search(self, query: str, top_k: int | None = None) -> list[dict[str, Any]]:
        """
        搜索与查询相关的文档

        Args:
            query: 查询文本
            top_k: 返回的最相关文档数量，如果为None则使用settings中的配置

        Returns:
            包含相关文档和相似度分数的列表
        """
        try:
            # 使用settings中的配置值
            top_k = settings.RETRIEVAL_TOP_K if top_k is None else top_k
            logger.info(f"Searching for query: {query}")
            results = (
                self.raw_search.search(query, top_k)
                if hasattr(self, "raw_search")
                else self.vector_store.similarity_search(query, top_k)
            )
            logger.info(f"Found {len(results)} relevant documents")
            return results
        except Exception as e:
            logger.error(f"Error in search: {e!s}")
            raise

    def retrieve_relevant_context(
        self,
        query: str,
        top_k: int | None = None,
        min_score: float | None = None,
        return_dict_list: bool = False,
    ):
        """
        检索与查询相关的上下文
        Args:
            query: 查询文本
            top_k: 返回的最相关文档数量，如果为None则使用settings中的配置
            min_score: 最小余弦阈值；旧配置默认 0.5，新模型必须显式指定
            return_dict_list: 是否返回文献分块字典列表
        Returns:
            版本化的证据 JSON 文本，或文献分块字典列表
        """
        try:
            if hasattr(self, "raw_search"):
                raise ValueError(
                    "Explicit retrieval profiles are raw-search only; context selection is not calibrated"
                )
            if min_score is None:
                if settings.EMBEDDING_PROFILE:
                    raise ValueError(
                        "Candidate context threshold is uncalibrated; use raw search or specify a threshold explicitly"
                    )
                min_score = 0.5
            if not math.isfinite(min_score) or not -1 <= min_score <= 1:
                raise ValueError(
                    "min_score must be a finite cosine threshold in [-1, 1]"
                )
            # 使用settings中的配置值
            top_k = settings.RETRIEVAL_TOP_K if top_k is None else top_k
            logger.info(f"Searching for query: {query}")
            results = self.vector_store.similarity_search(query, top_k)
            logger.info(f"Found {len(results)} relevant documents")

            if not results:
                logger.warning("No relevant documents found")
                return [] if return_dict_list else serialize_context([])

            # 过滤掉相似度分数低于阈值的文档
            filtered_results = [r for r in results if r["score"] >= min_score]

            if not filtered_results:
                logger.warning(
                    f"No documents found with similarity score >= {min_score}"
                )
                return [] if return_dict_list else serialize_context([])

            if return_dict_list:
                # 返回文献分块字典列表
                return [r["document"] for r in filtered_results]

            serialized = serialize_context([r["document"] for r in filtered_results])
            logger.info(
                "Retrieved versioned evidence JSON, length: %s", len(serialized)
            )
            return serialized
        except Exception as e:
            logger.error(f"Error in retrieve_relevant_context: {e!s}")
            raise
