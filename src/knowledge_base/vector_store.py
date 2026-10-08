from __future__ import annotations

import json
import os
from pathlib import Path
from typing import TYPE_CHECKING, Any

import numpy as np

from config.settings import settings
from src.knowledge_base.identity import (
    merge_chunk_metadata,
    normalize_chunk,
    unique_chunks,
)
from src.knowledge_base.similarity import cosine_scores, top_indices
from src.knowledge_base.token_budget import TokenBudget
from src.utils.artifacts import atomic_text_writer, sha256_file
from src.utils.logger import logger

if TYPE_CHECKING:
    from sentence_transformers import SentenceTransformer


class VectorStore:
    def __init__(self, *, load_index: bool = True, device: str = "auto"):
        """初始化向量存储"""
        if settings.EMBEDDING_PROFILE:
            from config.settings import resolve_path
            from src.knowledge_base.embedding import CandidateEncoder, profile_from_file

            profile, _ = profile_from_file(resolve_path(settings.EMBEDDING_PROFILE))
            self.encoder = CandidateEncoder(profile, device=device)
            self.model = self.encoder.model
            self.budget = self.encoder
        else:
            self.model = self._load_model()
            if device != "auto":
                self.model.to(device)
            self.budget = TokenBudget(self.model)
        self.vector_index = (
            self._load_vector_index()
            if load_index
            else {"documents": [], "vectors": []}
        )
        logger.info("Vector store initialized successfully")

    def _load_model(self) -> SentenceTransformer:
        """加载文本向量化模型"""
        # Settings must load .env before Hugging Face initializes cache paths.
        from sentence_transformers import SentenceTransformer

        try:
            # 使用预训练模型名称或本地模型路径
            model_name = settings.EMBEDDING_MODEL
            logger.info(f"Loading model: {model_name}")

            # 如果是本地模型路径，使用完整路径
            if os.path.exists(os.path.join(settings.MODEL_DIR, model_name)):
                model_path = os.path.join(settings.MODEL_DIR, model_name)
                logger.info(f"Using local model from {model_path}")
                model = SentenceTransformer(model_path)
            else:
                # 否则使用预训练模型名称
                logger.info(f"Using pretrained model: {model_name}")
                model = SentenceTransformer(
                    model_name, revision=settings.EMBEDDING_MODEL_REVISION
                )
            return model
        except Exception as e:
            logger.error(f"Error loading model: {e!s}")
            raise

    def _load_vector_index(self) -> dict[str, Any]:
        """加载向量索引"""
        try:
            binary_path = Path(settings.VECTOR_DB_DIR) / "storage.json"
            if binary_path.exists():
                from src.knowledge_base.binary_index import BinaryIndex

                if not hasattr(self, "encoder"):
                    raise ValueError(
                        "Binary candidate requires its explicit embedding profile"
                    )
                self.storage = BinaryIndex(
                    Path(settings.VECTOR_DB_DIR),
                    expected_embedding=self.encoder.manifest(),
                )
                self.index_sha256 = self.storage.index_sha256
                return {
                    "documents": self.storage.documents,
                    "vectors": self.storage.vectors,
                    "embedding": self.storage.spec["embedding"],
                    "chunking": self.storage.spec["chunking"],
                }
            index_path = os.path.join(settings.VECTOR_DB_DIR, "vector_index.json")
            logger.info(f"Loading vector index from {index_path}")

            if not os.path.exists(index_path):
                raise FileNotFoundError(
                    f"Vector index not found: {index_path}. Build or select an index explicitly."
                )

            self.index_sha256 = sha256_file(Path(index_path))
            manifest_path = Path(settings.VECTOR_DB_DIR) / "run.json"
            if manifest_path.is_file():
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                if (
                    manifest.get("schema") != "chemqa-artifact-run-v1"
                    or manifest.get("kind") != "indexes"
                    or manifest.get("status") != "ready"
                ):
                    raise ValueError("Selected candidate index is not ready")
                expected = manifest.get("files", {})
                if expected.get("vector_index.json") != self.index_sha256:
                    raise ValueError("Candidate index checksum mismatch")
                if expected.get("processed_chunks.json") != sha256_file(
                    Path(settings.VECTOR_DB_DIR) / "processed_chunks.json"
                ):
                    raise ValueError("Candidate processed-data checksum mismatch")

            with open(index_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            if "documents" not in data or "vectors" not in data:
                raise ValueError("Legacy index lacks chunk text; rebuild it explicitly")
            if len(data["documents"]) != len(data["vectors"]):
                raise ValueError("Index documents and vectors have different lengths")
            # Old structured records receive IDs in memory, never via an implicit disk rewrite.
            data["documents"] = [normalize_chunk(doc) for doc in data["documents"]]
            if len({d["chunk_id"] for d in data["documents"]}) != len(
                data["documents"]
            ):
                raise ValueError(
                    "Duplicate chunk IDs; run scripts.migrate_q01 before loading"
                )
            if (
                data.get("embedding")
                and hasattr(self, "budget")
                and data["embedding"] != self.budget.manifest()
            ):
                raise ValueError(
                    "Index embedding configuration differs; rebuild explicitly"
                )
            data["vectors"] = np.asarray(data["vectors"])
            if hasattr(self, "encoder") and (
                not data.get("embedding")
                or data["vectors"].shape
                != (len(data["documents"]), self.encoder.profile["dimension"])
                or not np.isfinite(data["vectors"]).all()
                or not np.allclose(
                    np.linalg.norm(data["vectors"], axis=1), 1, atol=1e-4
                )
            ):
                raise ValueError(
                    "Candidate vectors lack a compatible profile, dimension or normalization"
                )

            return data
        except Exception as e:
            logger.error(f"Error loading vector index: {e!s}")
            raise

    def _save_vector_index(self, data: dict[str, Any] | None = None):
        """保存向量索引到文件"""
        try:
            self._require_mutable_index()
            index_path = os.path.join(settings.VECTOR_DB_DIR, "vector_index.json")

            # 如果没有提供数据，使用当前索引
            if data is None:
                data = self.vector_index

            # 将numpy数组转换为列表以便JSON序列化
            save_data = {
                **{k: v for k, v in data.items() if k not in ("documents", "vectors")},
                "documents": data["documents"],
                "vectors": np.asarray(data["vectors"]).tolist(),
            }

            with atomic_text_writer(Path(index_path)) as f:
                json.dump(save_data, f, ensure_ascii=False, indent=2)

            self.index_sha256 = sha256_file(Path(index_path))

            logger.info(f"Vector index saved to {index_path}")

        except Exception as e:
            logger.error(f"Error saving vector index: {e!s}")
            raise

    def encode_texts(self, texts: str | list[str], **kwargs):
        """Reject over-limit inputs instead of letting the encoder silently truncate."""
        if hasattr(self, "encoder"):
            return self.encoder.encode(texts, kind="document", **kwargs)
        if hasattr(self, "budget"):
            self.budget.check([texts] if isinstance(texts, str) else texts)
        return self.model.encode(texts, **kwargs)

    def score_query(self, query: str) -> np.ndarray:
        """Cosine scores aligned with every stored document, without re-encoding it."""
        documents = self.vector_index.get("documents", [])
        vectors = self.vector_index.get("vectors", [])
        if len(documents) != len(vectors):
            raise ValueError("Index documents and vectors have different lengths")
        if not documents:
            return np.empty(0, dtype=np.float64)
        query_vector = (
            self.encoder.encode(query, kind="query")
            if hasattr(self, "encoder")
            else self.encode_texts(query)
        )
        return cosine_scores(vectors, query_vector)

    def similarity_search(self, query: str, top_k: int = 3) -> list[dict[str, Any]]:
        """
        执行余弦相似度搜索，score 范围为 [-1, 1]

        Args:
            query: 查询文本
            top_k: 返回的最相关文档数量

        Returns:
            包含文档和相似度分数的列表，每个元素格式为:
            {
                "document": {
                    "text": str,
                    "source": str,
                    "chunk_index": int
                },
                "score": float
            }
        """
        try:
            # Validate the count even for an empty index; zero requests encode nothing.
            top_indices(np.empty(0), top_k)
            if top_k == 0 or not self.vector_index.get("documents"):
                return []
            if hasattr(self, "storage"):
                query_vector = self.encoder.encode(query, kind="query")
                return self.storage.search(query_vector, top_k)
            scores = self.score_query(query)
            selected = top_indices(scores, top_k)
            top_scores = scores[selected]

            # 构建标准化的结果
            results = []
            for idx, score in zip(selected, top_scores):
                doc = self.vector_index["documents"][idx]
                # 确保文档格式符合预期
                result = {"document": dict(doc), "score": float(score)}
                results.append(result)

            logger.info(
                f"Found {len(results)} relevant documents for query: {query[:50]}..."
            )
            return results
        except Exception as e:
            logger.error(f"Error in similarity search: {e!s}")
            raise

    def add_documents(self, documents: list[dict[str, Any]]):
        """
        添加文档到向量存储

        Args:
            documents: 文档列表，每个文档必须包含text字段，可选包含source和chunk_index字段
        """
        try:
            self._require_mutable_index()
            incoming = unique_chunks(documents)
            existing = {doc["chunk_id"]: doc for doc in self.vector_index["documents"]}
            new_docs = []
            for doc in incoming:
                if doc["chunk_id"] in existing:
                    current = existing[doc["chunk_id"]]
                    merge_chunk_metadata(current, doc)
                else:
                    new_docs.append(doc)
            if new_docs:
                if (
                    hasattr(self, "budget")
                    and self.vector_index["documents"]
                    and not self.vector_index.get("embedding")
                ):
                    raise ValueError(
                        "Rebuild the legacy index before adding new token-based chunks"
                    )
                if hasattr(self, "budget"):
                    self.vector_index["embedding"] = self.budget.manifest()
                vectors = np.asarray(
                    self.encode_texts([doc["text"] for doc in new_docs])
                )
                current = np.asarray(self.vector_index["vectors"])
                self.vector_index["vectors"] = (
                    np.vstack([current, vectors]) if current.size else vectors
                )
                self.vector_index["documents"].extend(new_docs)
            if incoming:
                self._save_vector_index()
            logger.info(
                "Added %s new chunks; duplicate imports reuse existing IDs",
                len(new_docs),
            )

        except Exception as e:
            logger.error(f"Error adding documents: {e!s}")
            raise

    @staticmethod
    def _require_mutable_index():
        if (Path(settings.VECTOR_DB_DIR) / "run.json").exists():
            raise ValueError(
                "Published candidate indexes are immutable; build a new candidate"
            )
