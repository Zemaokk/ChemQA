"""Verify cosine retrieval/heatmap agreement using the existing index, without API calls."""

import argparse
import hashlib
import json
from pathlib import Path
from unittest.mock import patch

import numpy as np

from config.settings import settings
from src.visualization.heatmap import HeatmapVisualizer


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--heatmap", type=Path)
    args = parser.parse_args()
    index_path = Path(settings.VECTOR_DB_DIR) / "vector_index.json"
    processed_path = Path(settings.PROCESSED_DIR) / "processed_chunks.json"
    before = {
        p.name: hashlib.sha256(p.read_bytes()).hexdigest()
        for p in (index_path, processed_path)
    }
    visualizer = HeatmapVisualizer()
    store = visualizer.retriever.vector_store
    docs, vectors = store.vector_index["documents"], store.vector_index["vectors"]
    queries = visualizer.generate_organic_electrocatalysis_queries()
    norms = np.linalg.norm(vectors, axis=1)
    query_reports = []
    max_difference = 0.0
    with patch.object(store.model, "encode", wraps=store.model.encode) as encode:
        data = visualizer.prepare_similarity_data(queries, max_docs=15)
        for column, query in enumerate(queries):
            query_vector = np.asarray(store.encode_texts(query), dtype=np.float64)
            # Independent formula using the untouched on-disk vectors.
            expected = (vectors @ query_vector) / norms / np.linalg.norm(query_vector)
            np.testing.assert_allclose(
                data["matrix"][:, column], expected, atol=1e-12, rtol=0
            )
            max_difference = max(
                max_difference,
                float(np.max(np.abs(data["matrix"][:, column] - expected))),
            )
            results = visualizer.retriever.search(query, top_k=10)
            selected = np.argsort(-expected, kind="stable")[:10]
            if [r["document"]["chunk_id"] for r in results] != [
                docs[i]["chunk_id"] for i in selected
            ]:
                raise ValueError(
                    "Retrieval rank differs from independent cosine scores"
                )
            np.testing.assert_allclose(
                [r["score"] for r in results],
                data["matrix"][selected, column],
                atol=1e-12,
                rtol=0,
            )
            dot_top = np.argsort(-(vectors @ query_vector), kind="stable")[:10]
            query_reports.append(
                {
                    "query": query,
                    "top_10_chunk_ids": [r["document"]["chunk_id"] for r in results],
                    "top_10_cosine_scores": [r["score"] for r in results],
                    "top_10_overlap_with_old_dot_product": len(
                        set(selected) & set(dot_top)
                    ),
                    "chunks_at_default_cosine_threshold": int(
                        np.count_nonzero(expected >= 0.5)
                    ),
                }
            )
        # A single-query plot selects exactly the same rows as a search of that size.
        single = visualizer.prepare_similarity_data([queries[0]], max_docs=10)
        if single["chunk_ids"] != query_reports[0]["top_10_chunk_ids"]:
            raise ValueError(
                "Single-query heatmap and retrieval select different chunks"
            )
        expected_selection = np.argsort(-data["matrix"].mean(axis=1), kind="stable")[
            :15
        ]
        np.testing.assert_array_equal(data["selected_indices"], expected_selection)
        if args.heatmap:
            args.heatmap.parent.mkdir(parents=True, exist_ok=True)
            visualizer.create_similarity_heatmap(
                queries, max_docs=15, save_path=str(args.heatmap)
            )
        calls = [c.args[0] for c in encode.call_args_list]
        if any(text not in queries for text in calls):
            raise ValueError(
                "Visualization re-encoded a document instead of reusing indexed vectors"
            )
    after = {
        p.name: hashlib.sha256(p.read_bytes()).hexdigest()
        for p in (index_path, processed_path)
    }
    if before != after:
        raise ValueError("Read-only validation changed indexed data")
    report = {
        "metric": "cosine",
        "rows": len(docs),
        "dimensions": vectors.shape[1],
        "document_vector_norm_percentiles": np.percentile(
            norms, [0, 50, 90, 100]
        ).tolist(),
        "maximum_score_difference_from_independent_formula": max_difference,
        "retrieval_and_heatmap_scores_match": True,
        "single_query_rank_matches": True,
        "multi_query_selection": "mean_cosine",
        "query_encoding_calls": len(calls),
        "document_encoding_calls": 0,
        "data_files_unchanged": True,
        "sha256": after,
        "queries": query_reports,
        "quality_evaluation": "Not evaluated; score agreement does not establish retrieval quality.",
    }
    serialized = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    print(serialized)
    if args.report:
        args.report.write_text(serialized, encoding="utf-8")


if __name__ == "__main__":
    main()
