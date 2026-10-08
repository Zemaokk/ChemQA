"""Verified, optional reranking of the frozen G candidate window."""

import json

import numpy as np

from config.settings import resolve_path
from src.knowledge_base.hybrid_search import HybridSearch
from src.knowledge_base.reranker import QwenReranker, validate_profile
from src.knowledge_base.similarity import top_indices
from src.utils.artifacts import sha256_file


class RerankedSearch:
    @classmethod
    def from_profile(cls, vector_store, path, *, device="auto"):
        path = resolve_path(path)
        run = json.loads((path.parent / "run.json").read_text())
        if (
            run.get("schema") != "chemqa-artifact-run-v1"
            or run.get("kind") != "rerank_runs"
            or run.get("status") != "ready"
            or run.get("files", {}).get(path.name) != sha256_file(path)
        ):
            raise ValueError("Reranker profile is not a verified ready artifact")
        spec = json.loads(path.read_text())
        if (
            spec.get("schema") != "chemqa-reranked-search-v1"
            or type(spec.get("enabled")) is not bool
            or spec.get("candidate_window") != 50
            or spec.get("score_policy") != "raw_only_no_context_threshold"
        ):
            raise ValueError("Invalid reranked search profile")
        validate_profile(spec["model_profile"])
        model_path = path.parent / "model_profile.json"
        if (
            run["files"].get(model_path.name) != sha256_file(model_path)
            or json.loads(model_path.read_text()) != spec["model_profile"]
        ):
            raise ValueError("Frozen reranker model profile changed")
        retrieval_path = resolve_path(spec["retrieval_profile"])
        if (
            spec["retrieval_run_sha256"]
            != sha256_file(retrieval_path.parent / "run.json")
            or run.get("source_G_run_sha256") != spec["retrieval_run_sha256"]
        ):
            raise ValueError("Frozen source G run changed")
        instance = cls()
        instance.retrieval = HybridSearch.from_profile(vector_store, retrieval_path)
        if instance.retrieval.window != 50:
            raise ValueError("Reranking requires the frozen 50-candidate window")
        instance.reranker = None
        if spec["enabled"]:
            instance.reranker = QwenReranker(spec["model_profile"], device=device)
            if (
                instance.reranker.template_sha256
                != spec["model_profile"]["chat_template_sha256"]
            ):
                raise ValueError("Frozen reranker template changed")
        return instance

    def search(self, query, top_k=10):
        top_indices(np.empty(0), top_k)
        if top_k > 50:
            raise ValueError("Result count exceeds frozen candidate window")
        if top_k == 0:
            return []
        if self.reranker is None:
            return self.retrieval.search(query, top_k)
        hits = self.retrieval.search(query, 50)
        return self.reranker.rerank(query, hits)[:top_k]
