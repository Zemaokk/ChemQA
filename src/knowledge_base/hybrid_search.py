"""Explicit raw retrieval profiles; RRF scores never enter cosine threshold filtering."""

import json
import math

import numpy as np

from config.settings import resolve_path
from src.knowledge_base.lexical_index import BM25Index, dense_binding
from src.knowledge_base.similarity import top_indices
from src.utils.artifacts import sha256_file


def fuse_rrf(routes, row_order, *, constant=60):
    if type(constant) is not int or constant <= 0:
        raise ValueError("RRF constant must be a positive integer")
    merged = {}
    for name, hits in routes.items():
        seen = set()
        for rank, hit in enumerate(hits, 1):
            cid = hit["document"]["chunk_id"]
            if cid in seen:
                continue
            seen.add(cid)
            if cid not in row_order or not math.isfinite(hit["score"]):
                raise ValueError("RRF input has unknown identity or nonfinite score")
            entry = merged.setdefault(
                cid,
                {
                    "document": hit["document"],
                    "score": 0.0,
                    "score_kind": "rrf",
                    "row_id": row_order[cid],
                    "routes": {},
                },
            )
            if entry["document"] != hit["document"]:
                raise ValueError("Conflicting metadata for shared candidate identity")
            entry["score"] += 1 / (constant + rank)
            entry["routes"][name] = {
                "rank": rank,
                "score": hit["score"],
                "score_kind": hit.get("score_kind", "cosine"),
            }
    return sorted(merged.values(), key=lambda hit: (-hit["score"], hit["row_id"]))


class HybridSearch:
    def __init__(
        self, vector_store, lexical_directory, *, window=50, constant=60, mode="hybrid"
    ):
        if (
            type(window) is not int
            or window <= 0
            or type(constant) is not int
            or constant <= 0
            or mode not in {"dense", "bm25", "hybrid"}
        ):
            raise ValueError("Invalid raw retrieval configuration")
        if not hasattr(vector_store, "storage"):
            raise ValueError(
                "Hybrid retrieval requires the frozen binary dense candidate"
            )
        self.vector_store = vector_store
        self.window, self.constant, self.mode = window, constant, mode
        self.lexical = BM25Index(
            lexical_directory,
            vector_store.storage.documents,
            dense_binding(vector_store.storage),
        )
        self.row_order = {
            doc["chunk_id"]: i for i, doc in enumerate(vector_store.storage.documents)
        }

    @classmethod
    def from_profile(cls, vector_store, path):
        path = resolve_path(path)
        run = json.loads((path.parent / "run.json").read_text())
        if (
            run.get("schema") != "chemqa-artifact-run-v1"
            or run.get("kind") != "hybrid_runs"
            or run.get("status") != "ready"
            or run.get("files", {}).get(path.name) != sha256_file(path)
        ):
            raise ValueError("Retrieval profile is not a verified ready artifact")
        spec = json.loads(path.read_text())
        if (
            spec.get("schema") != "chemqa-retrieval-profile-v1"
            or spec.get("binding") != dense_binding(vector_store.storage)
            or spec.get("score_policy") != "raw_only_no_context_threshold"
            or spec.get("fusion") != "equal_weight_rrf"
            or spec.get("deduplication") != "chunk_id_first_occurrence_per_route"
        ):
            raise ValueError("Retrieval profile/dense configuration mismatch")
        lexical = resolve_path(spec["lexical_directory"])
        if spec.get("lexical_run_sha256") != sha256_file(lexical / "run.json"):
            raise ValueError("Lexical artifact changed since profile publication")
        return cls(
            vector_store,
            lexical,
            window=spec["route_window"],
            constant=spec["rrf_constant"],
            mode=spec["mode"],
        )

    def routes(self, query, *, query_vector=None):
        dense = (
            self.vector_store.storage.search(query_vector, self.window)
            if query_vector is not None
            else self.vector_store.similarity_search(query, self.window)
        )
        dense = [
            {
                **hit,
                "row_id": self.row_order[hit["document"]["chunk_id"]],
                "score_kind": "cosine",
            }
            for hit in dense
        ]
        bm25 = self.lexical.search(query, self.window)
        fused = fuse_rrf(
            {"dense": dense, "bm25": bm25}, self.row_order, constant=self.constant
        )
        return {"dense": dense, "bm25": bm25, "hybrid": fused[: self.window]}

    def search(self, query, top_k=10):
        top_indices(np.empty(0), top_k)
        if top_k > self.window:
            raise ValueError("Result count exceeds frozen route window")
        if top_k == 0:
            return []
        if self.mode == "bm25":
            return self.lexical.search(query, top_k)
        if self.mode == "dense":
            return self.vector_store.similarity_search(query, top_k)
        return self.routes(query)["hybrid"][:top_k]
