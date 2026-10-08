"""Lexical normalization, independent BM25 values, RRF and profile safety contracts."""

import copy
import json
import math
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import numpy as np

from scripts.validate_q065g import choose_mode, evaluate
from src.knowledge_base.hybrid_search import HybridSearch, fuse_rrf
from src.knowledge_base.lexical_index import (
    FILES,
    BM25Index,
    analyze,
    build_lexical,
    dense_binding,
)
from src.knowledge_base.retriever import Retriever
from src.utils.artifacts import sha256_file


def docs(texts):
    return [
        {"text": text, "doc_id": "paper" + str(i // 2), "chunk_id": "chunk" + str(i)}
        for i, text in enumerate(texts)
    ]


def hit(row, score=1.0):
    return {
        "document": {"chunk_id": "c" + str(row), "text": "t" + str(row)},
        "score": score,
        "score_kind": "cosine",
    }


class LexicalAnalysisTests(unittest.TestCase):
    def test_formula_subscripts_charge_and_width_have_same_search_tokens(self):
        self.assertEqual(analyze("H₃O⁺ HSO₄− ＣＯ₂"), analyze("H3O+ HSO4- CO2"))
        self.assertIn("chem:HSO4-", analyze("HSO₄−"))

    def test_formula_case_alias_distinguishes_CO_and_Co(self):
        self.assertIn("chem:CO", analyze("CO"))
        self.assertIn("chem:Co", analyze("Co"))
        self.assertNotIn("chem:CO", analyze("Co"))

    def test_signed_numbers_exponents_and_units_survive(self):
        terms = analyze("−0.25 V 1E-3 mA cm⁻²")
        self.assertIn("n:-0.25", terms)
        self.assertNotIn("n:0.25", terms)
        self.assertIn("n:1e-3", terms)
        self.assertIn("w:ma", terms)
        self.assertIn("w:v", terms)

    def test_cjk_bigrams_hyphen_aliases_and_no_translation(self):
        terms = analyze("苄醇 electro-oxidation")
        self.assertIn("c:苄醇", terms)
        self.assertIn("w:electro-oxidation", terms)
        self.assertIn("w:oxidation", terms)
        self.assertNotIn("w:benzyl", terms)
        self.assertEqual(analyze("the and of"), [])


class BM25Tests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name)
        self.documents = docs(["catalyst catalyst", "catalyst", "water"])
        self.binding = {"fixed": "row-order"}
        build_lexical(self.path, self.documents, self.binding)
        self.publish()

    def publish(self, **changes):
        (self.path / "run.json").write_text(
            json.dumps(
                {
                    "schema": "chemqa-artifact-run-v1",
                    "kind": "lexical_indexes",
                    "status": "ready",
                    "files": {n: sha256_file(self.path / n) for n in FILES},
                    **changes,
                }
            )
        )

    def load(self):
        return BM25Index(self.path, self.documents, self.binding)

    def test_scores_match_hand_calculated_bm25_and_binary_query_frequency(self):
        index = self.load()
        idf = math.log(1 + 1.5 / 2.5)
        expected = [idf * 4.4 / 3.65, idf * 2.2 / 1.975, 0]
        np.testing.assert_allclose(index.scores("catalyst"), expected, atol=1e-14)
        np.testing.assert_array_equal(
            index.scores("catalyst catalyst"), index.scores("catalyst")
        )
        self.assertEqual([h["row_id"] for h in index.search("catalyst", 50)], [0, 1])

    def test_unmatched_and_empty_queries_do_not_return_zero_score_rows(self):
        index = self.load()
        for query in ["", "nonexistent", "苄醇", "the and"]:
            self.assertEqual(index.search(query), [])
        self.assertEqual(index.search(None, 0), [])
        for k in [-1, True, 1.5]:
            with self.assertRaises(ValueError):
                index.search("water", k)

    def test_deterministic_ties_and_empty_documents(self):
        with tempfile.TemporaryDirectory() as path:
            documents = docs(["same", "same", ""])
            build_lexical(Path(path), documents, self.binding)
            index = BM25Index(Path(path), documents, self.binding, staging=True)
            self.assertEqual([h["row_id"] for h in index.search("same", 10)], [0, 1])
            self.assertEqual(int(index.lengths[2]), 0)

    def test_ready_checksums_and_binding_rejected_on_mismatch(self):
        with self.assertRaisesRegex(ValueError, "binding"):
            BM25Index(self.path, self.documents, {"fixed": "other"})
        for name in FILES:
            data = (self.path / name).read_bytes()
            (self.path / name).write_bytes(data + b"corrupt")
            with self.assertRaisesRegex(ValueError, "checksum"):
                self.load()
            (self.path / name).write_bytes(data)
        self.publish(status="running")
        with self.assertRaisesRegex(ValueError, "ready"):
            self.load()

    def test_internal_posting_frequency_corruption_rejected(self):
        with np.load(self.path / "postings.npz", allow_pickle=False) as archive:
            arrays = {name: archive[name] for name in archive.files}
        arrays["frequencies"][0] += 1
        np.savez_compressed(self.path / "postings.npz", **arrays)
        self.publish()
        with self.assertRaisesRegex(ValueError, "lengths"):
            self.load()

    def test_internal_vocabulary_or_analyzer_corruption_rejected(self):
        spec = json.loads((self.path / "lexical.json").read_text())
        spec["analyzer_version"] = "wrong"
        (self.path / "lexical.json").write_text(json.dumps(spec))
        self.publish()
        with self.assertRaisesRegex(ValueError, "profile"):
            self.load()

    def test_rebuild_cannot_overwrite_and_empty_corpus_fails(self):
        with self.assertRaisesRegex(ValueError, "overwrite"):
            build_lexical(self.path, self.documents, self.binding)
        with (
            tempfile.TemporaryDirectory() as path,
            self.assertRaisesRegex(ValueError, "empty"),
        ):
            build_lexical(Path(path), docs([""]), self.binding)


class FusionTests(unittest.TestCase):
    def test_rrf_hand_values_and_cross_route_deduplication(self):
        routes = {"dense": [hit(0), hit(1)], "bm25": [hit(1, 30), hit(2, 20)]}
        merged = fuse_rrf(routes, {"c0": 0, "c1": 1, "c2": 2})
        self.assertEqual(
            [h["document"]["chunk_id"] for h in merged], ["c1", "c0", "c2"]
        )
        self.assertAlmostEqual(merged[0]["score"], 1 / 62 + 1 / 61)
        self.assertEqual(set(merged[0]["routes"]), {"dense", "bm25"})
        self.assertEqual(merged[0]["score_kind"], "rrf")

    def test_duplicate_within_route_never_adds_another_vote(self):
        merged = fuse_rrf({"dense": [hit(0), hit(0), hit(1)]}, {"c0": 0, "c1": 1})
        self.assertEqual(len(merged), 2)
        self.assertEqual(merged[0]["score"], 1 / 61)
        self.assertEqual(merged[1]["routes"]["dense"]["rank"], 3)

    def test_equal_rrf_scores_tie_by_original_row_and_empty_branch_is_valid(self):
        merged = fuse_rrf({"dense": [hit(1)], "bm25": [hit(0)]}, {"c0": 0, "c1": 1})
        self.assertEqual([h["row_id"] for h in merged], [0, 1])
        self.assertEqual(len(fuse_rrf({"dense": [hit(0)], "bm25": []}, {"c0": 0})), 1)

    def test_unknown_nonfinite_conflicting_metadata_and_invalid_constant_fail(self):
        for route, order, k in [
            ({"dense": [hit(0)]}, {}, 60),
            ({"dense": [hit(0, float("nan"))]}, {"c0": 0}, 60),
            ({"dense": [hit(0)]}, {"c0": 0}, 0),
        ]:
            with self.assertRaises(ValueError):
                fuse_rrf(route, order, constant=k)
        bad = copy.deepcopy(hit(0))
        bad["document"]["text"] = "changed"
        with self.assertRaisesRegex(ValueError, "Conflicting"):
            fuse_rrf({"dense": [hit(0)], "bm25": [bad]}, {"c0": 0})


class HybridIntegrationTests(unittest.TestCase):
    def test_candidate_selection_requires_all_frozen_gates(self):
        def summary(recall, coverage=0.5, docs=0.8):
            return {
                "at_k": {
                    "5": {"mean_anchor_character_coverage": coverage},
                    "10": {
                        "complete_anchor_recall": recall,
                        "annotated_doc_recall": docs,
                    },
                }
            }

        base = summary(0.5)
        self.assertEqual(choose_mode({"dense": base, "hybrid": summary(0.6)}), "hybrid")
        for changed in [
            summary(0.5),
            summary(0.4),
            summary(0.6, 0.4),
            summary(0.6, docs=0.7),
        ]:
            self.assertEqual(choose_mode({"dense": base, "hybrid": changed}), "dense")

    def test_reserve_query_guard_prevents_any_route_ranking(self):
        engine = Mock()
        with (
            patch("scripts.validate_q065g.HybridSearch", return_value=engine),
            self.assertRaisesRegex(ValueError, "Reserve"),
        ):
            evaluate(
                Mock(),
                [np.ones(3)],
                [{"split": "reserve", "question_id": "R01"}],
                Path("unused"),
                {"route_window": 50, "rrf_constant": 60},
                {"records": [{"question_id": "R01"}]},
            )
        engine.routes.assert_not_called()

    def test_explicit_retriever_profile_uses_raw_search_and_blocks_context_threshold(
        self,
    ):
        store = Mock()
        raw = Mock()
        raw.search.return_value = [hit(0)]
        with (
            patch("src.knowledge_base.retriever.VectorStore", return_value=store),
            patch.object(HybridSearch, "from_profile", return_value=raw),
        ):
            retriever = Retriever(retrieval_profile="profile.json")
            self.assertEqual(retriever.search("query", 2), [hit(0)])
            raw.search.assert_called_once_with("query", 2)
            for threshold in [None, 0, 0.5]:
                with self.assertRaisesRegex(ValueError, "raw-search only"):
                    retriever.retrieve_relevant_context("query", min_score=threshold)
        store.similarity_search.assert_not_called()

    def test_published_profile_checks_hash_dense_binding_and_lexical_identity(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            documents = docs(["catalyst"])
            storage = SimpleNamespace(
                documents=documents,
                index_sha256="frozen",
                spec={
                    "documents_sha256": "rows",
                    "row_count": 1,
                    "embedding": {"model": "fixed"},
                },
            )
            store = SimpleNamespace(storage=storage)
            lexical = root / "lexical"
            binding = dense_binding(storage)
            build_lexical(lexical, documents, binding)
            (lexical / "run.json").write_text(
                json.dumps(
                    {
                        "schema": "chemqa-artifact-run-v1",
                        "kind": "lexical_indexes",
                        "status": "ready",
                        "files": {n: sha256_file(lexical / n) for n in FILES},
                    }
                )
            )
            profile = {
                "schema": "chemqa-retrieval-profile-v1",
                "mode": "hybrid",
                "binding": binding,
                "lexical_directory": str(lexical),
                "lexical_run_sha256": sha256_file(lexical / "run.json"),
                "score_policy": "raw_only_no_context_threshold",
                "fusion": "equal_weight_rrf",
                "deduplication": "chunk_id_first_occurrence_per_route",
                "route_window": 50,
                "rrf_constant": 60,
            }
            path = root / "retrieval_profile.json"

            def publish(value):
                path.write_text(json.dumps(value))
                (root / "run.json").write_text(
                    json.dumps(
                        {
                            "schema": "chemqa-artifact-run-v1",
                            "kind": "hybrid_runs",
                            "status": "ready",
                            "files": {path.name: sha256_file(path)},
                        }
                    )
                )

            publish(profile)
            self.assertEqual(HybridSearch.from_profile(store, path).mode, "hybrid")
            path.write_text(path.read_text() + " ")
            with self.assertRaisesRegex(ValueError, "verified"):
                HybridSearch.from_profile(store, path)
            publish({**profile, "binding": {"wrong": True}})
            with self.assertRaisesRegex(ValueError, "mismatch"):
                HybridSearch.from_profile(store, path)
            publish({**profile, "lexical_run_sha256": "wrong"})
            with self.assertRaisesRegex(ValueError, "changed"):
                HybridSearch.from_profile(store, path)

    def test_zero_request_encodes_nothing_and_window_cannot_expand(self):
        engine = HybridSearch.__new__(HybridSearch)
        engine.window = 50
        engine.mode = "hybrid"
        engine.vector_store = Mock()
        self.assertEqual(engine.search("question", 0), [])
        with self.assertRaisesRegex(ValueError, "window"):
            engine.search("question", 51)
        engine.vector_store.similarity_search.assert_not_called()

    def test_raw_profile_counts_and_modes_are_validated(self):
        for args in [
            {"window": 0},
            {"window": True},
            {"constant": 0},
            {"mode": "unknown"},
        ]:
            with self.assertRaises(ValueError):
                HybridSearch(Mock(), Path("unused"), **args)
        plain = SimpleNamespace()
        with self.assertRaisesRegex(ValueError, "binary"):
            HybridSearch(plain, Path("unused"))


if __name__ == "__main__":
    unittest.main()
