"""Cosine ranking, visualization agreement and invalid-vector handling."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, call, patch

import numpy as np

from src.knowledge_base.identity import document_id, normalize_chunk
from src.knowledge_base.retriever import Retriever
from src.knowledge_base.similarity import cosine_scores
from src.knowledge_base.vector_store import VectorStore
from src.visualization.heatmap import HeatmapVisualizer


def make_store(vectors=None):
    matrix = (
        np.array([[1, 0], [10, 10], [-1, 0], [0, 4]], dtype=float)
        if vectors is None
        else np.asarray(vectors, dtype=float)
    )
    store = VectorStore.__new__(VectorStore)
    store.vector_index = {
        "documents": [
            normalize_chunk(
                {
                    "doc_id": document_id(f"PDF {i}".encode()),
                    "source": f"{i}.pdf",
                    "text": f"evidence {i}",
                    "chunk_index": 0,
                }
            )
            for i in range(len(matrix))
        ],
        "vectors": matrix,
    }
    store.model = Mock()
    store.model.encode.return_value = np.array([2.0, 0.0])
    return store


def visualizer(store):
    plotter = HeatmapVisualizer.__new__(HeatmapVisualizer)
    plotter.retriever = Retriever.__new__(Retriever)
    plotter.retriever.vector_store = store
    return plotter


class SimilarityTests(unittest.TestCase):
    def test_cosine_corrects_magnitude_driven_dot_product_order(self):
        store = make_store()
        original = store.vector_index["vectors"].copy()
        self.assertEqual(np.argmax(original @ np.array([2, 0])), 1)
        results = store.similarity_search("query", 4)
        self.assertEqual(
            [r["document"]["source"] for r in results],
            ["0.pdf", "1.pdf", "3.pdf", "2.pdf"],
        )
        np.testing.assert_allclose([r["score"] for r in results], [1, 2**-0.5, 0, -1])
        np.testing.assert_array_equal(original, store.vector_index["vectors"])

    def test_positive_scaling_invariance_including_extreme_finite_magnitudes(self):
        vectors = np.array([[1, 2], [-2, 1], [3, -4]], dtype=float)
        query = np.array([2, 3], dtype=float)
        expected = cosine_scores(vectors, query)
        actual = cosine_scores(
            vectors * np.array([1e200, 1e-200, 9])[:, None], query * 1e300
        )
        np.testing.assert_allclose(actual, expected, atol=1e-15)

    def test_retrieval_and_single_query_heatmap_have_identical_scores_and_ids(self):
        store = make_store()
        results = store.similarity_search("query", 3)
        store.model.encode.reset_mock()
        data = visualizer(store).prepare_similarity_data(["query"], 3)
        self.assertEqual(
            data["chunk_ids"], [r["document"]["chunk_id"] for r in results]
        )
        np.testing.assert_array_equal(
            data["selected_matrix"][:, 0], [r["score"] for r in results]
        )
        store.model.encode.assert_called_once_with("query")

    def test_multiple_query_heatmap_uses_mean_cosine_and_only_encodes_queries(self):
        store = make_store()
        store.model.encode.side_effect = lambda q: (
            np.array([1, 0]) if q == "x" else np.array([0, 1])
        )
        data = visualizer(store).prepare_similarity_data(["x", "y"], 2)
        self.assertEqual(data["selected_indices"].tolist(), [1, 0])
        self.assertEqual(store.model.encode.call_args_list, [call("x"), call("y")])
        for column, query in enumerate(["x", "y"]):
            results = store.similarity_search(query, 4)
            by_id = {r["document"]["chunk_id"]: r["score"] for r in results}
            self.assertEqual(
                data["selected_matrix"][:, column].tolist(),
                [by_id[key] for key in data["chunk_ids"]],
            )

    def test_ties_keep_index_order_and_result_counts_are_bounded(self):
        store = make_store([[1, 0], [2, 0], [-1, 0]])
        self.assertEqual(
            [r["document"]["source"] for r in store.similarity_search("q", 99)],
            ["0.pdf", "1.pdf", "2.pdf"],
        )
        store.model.encode.reset_mock()
        self.assertEqual(visualizer(store).retriever.search("q", top_k=0), [])
        store.model.encode.assert_not_called()
        for count in (-1, 1.5, True):
            with self.assertRaises(ValueError):
                store.similarity_search("q", count)
            with self.assertRaises(ValueError):
                visualizer(store).prepare_similarity_data(["q"], count)

    def test_empty_index_and_no_selected_rows_do_not_encode(self):
        store = make_store(np.empty((0, 2)))
        self.assertEqual(store.similarity_search("q"), [])
        self.assertEqual(
            visualizer(store).prepare_similarity_data(["q"])["matrix"].shape, (0, 1)
        )
        store.model.encode.assert_not_called()
        with self.assertRaises(ValueError):
            visualizer(store).prepare_similarity_data([])
        store = make_store()
        self.assertEqual(
            visualizer(store)
            .prepare_similarity_data(["q"], 0)["selected_matrix"]
            .shape,
            (0, 1),
        )
        store.model.encode.assert_not_called()

    def test_zero_nonfinite_and_mismatched_vectors_fail_explicitly(self):
        bad_pairs = [
            ([[0, 0]], [1, 0]),
            ([[1, 0]], [0, 0]),
            ([[np.nan, 0]], [1, 0]),
            ([[1, np.inf]], [1, 0]),
            ([[1, 0]], [np.inf, 0]),
            ([[1, 0]], [1]),
            ([1, 0], [1, 0]),
            ([[1, 0]], [[1, 0]]),
        ]
        for vectors, query in bad_pairs:
            with (
                self.subTest(vectors=vectors, query=query),
                self.assertRaises(ValueError),
            ):
                cosine_scores(vectors, query)
        store = make_store()
        store.vector_index["documents"].pop()
        with self.assertRaisesRegex(ValueError, "different lengths"):
            store.score_query("q")

    def test_context_threshold_uses_cosine_and_validates_range(self):
        store = make_store()
        retriever = visualizer(store).retriever
        context = retriever.retrieve_relevant_context(
            "q", top_k=4, min_score=1, return_dict_list=True
        )
        self.assertEqual([d["source"] for d in context], ["0.pdf"])
        self.assertEqual(
            len(
                retriever.retrieve_relevant_context(
                    "q", min_score=0, return_dict_list=True
                )
            ),
            3,
        )
        for threshold in (float("nan"), float("inf"), -1.01, 1.01):
            with self.assertRaises(ValueError):
                retriever.retrieve_relevant_context("q", min_score=threshold)

    def test_render_uses_actual_selected_row_count_when_max_exceeds_index(self):
        import seaborn as sns

        store = make_store()
        plotter = visualizer(store)
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "heatmap.png"
            with patch(
                "src.visualization.heatmap.sns.heatmap", wraps=sns.heatmap
            ) as draw:
                plotter.create_similarity_heatmap(
                    ["q"], max_docs=15, save_path=str(path)
                )
            self.assertGreater(path.stat().st_size, 1000)
            self.assertEqual(
                draw.call_args.kwargs["yticklabels"],
                ["Chunk1", "Chunk2", "Chunk3", "Chunk4"],
            )
            self.assertEqual(draw.call_args.kwargs["vmin"], -1)
            self.assertEqual(draw.call_args.kwargs["vmax"], 1)
            store.model.encode.assert_called_once_with("q")


if __name__ == "__main__":
    unittest.main()
