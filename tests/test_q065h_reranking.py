"""Template integrity, ranking gates, frozen profiles and raw-score isolation."""

import copy
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import numpy as np
import torch

from scripts.validate_q065h import evaluate, select_enabled
from src.knowledge_base.hybrid_search import HybridSearch
from src.knowledge_base.reranked_search import RerankedSearch
from src.knowledge_base.reranker import QwenReranker, validate_profile
from src.knowledge_base.retriever import Retriever
from src.utils.artifacts import sha256_file

PROFILE = json.loads(Path("config/q065h_reranker.json").read_text())


def hit(i):
    return {
        "document": {"chunk_id": str(i), "text": "evidence" + str(i)},
        "score": 1 / (i + 1),
        "score_kind": "rrf",
    }


class Tokenizer:
    chat_template = "test-complete-template-v1"

    def apply_chat_template(self, messages, **_):
        return (
            "<start>"
            + "|".join(m["role"] + ":" + m["content"] for m in messages)
            + "<end>"
        )

    def __call__(self, texts, **_):
        return {"input_ids": [[ord(c) for c in t] for t in texts]}


class Model:
    max_seq_length = 4096
    device = "cpu"

    def __init__(self):
        self.tokenizer = Tokenizer()
        self.calls = 0
        self.corrupt = False
        self.output = None

    def eval(self):
        return self

    def preprocess(self, inputs, prompt):
        rows = [
            self.tokenizer.apply_chat_template(
                [
                    {"role": "system", "content": prompt},
                    {"role": "query", "content": q},
                    {"role": "document", "content": d},
                ]
            )
            for q, d in inputs
        ]
        ids = self.tokenizer(rows)["input_ids"]
        length = max(map(len, ids))
        padded = [[0] * (length - len(row)) + row for row in ids]
        masks = [[0] * (length - len(row)) + [1] * len(row) for row in ids]
        if self.corrupt:
            padded[0][-1] += 1
        return {
            "input_ids": torch.tensor(padded),
            "attention_mask": torch.tensor(masks),
        }

    def __call__(self, features):
        self.calls += 1
        count = len(features["input_ids"])
        return {
            "scores": self.output
            if self.output is not None
            else torch.arange(count).reshape(-1, 1).float()
        }


class TemplateTests(unittest.TestCase):
    def setUp(self):
        self.model = Model()
        self.engine = QwenReranker(PROFILE, model=self.model)

    def test_profile_requires_fixed_revision_and_supported_policy(self):
        for key, value in [
            ("revision", "main"),
            ("batch_size", True),
            ("max_sequence_tokens", 0),
            ("candidate_window", 100),
            ("score_kind", "probability"),
        ]:
            with self.subTest(key=key), self.assertRaises(ValueError):
                validate_profile({**PROFILE, key: value})

    def test_count_includes_instruction_query_document_and_special_template(self):
        pairs = [("q", "evidence"), ("longer query", "short")]
        _, counts = self.engine.prepare(pairs)
        self.assertEqual(counts, [len(self.engine.render(*p)) for p in pairs])
        self.assertGreater(
            counts[0], len(PROFILE["instruction"]) + len("q") + len("evidence")
        )
        self.assertEqual(self.model.tokenizer.padding_side, "left")

    def test_budget_overflow_fails_before_forward_without_truncation(self):
        self.engine.profile["max_sequence_tokens"] = 10
        with self.assertRaisesRegex(ValueError, "truncation is forbidden"):
            self.engine.score("q", [hit(0)])
        self.assertEqual(self.model.calls, 0)

    def test_equal_length_token_mutation_is_detected(self):
        self.model.corrupt = True
        with self.assertRaisesRegex(ValueError, "alter"):
            self.engine.score("q", [hit(0)])
        self.assertEqual(self.model.calls, 0)

    def test_empty_candidates_never_forward_and_duplicate_or_expanded_pool_fails(self):
        values, counts = self.engine.score("q", [])
        self.assertEqual(len(values), 0)
        self.assertEqual(counts, [])
        for hits in [[hit(0), hit(0)], [hit(i) for i in range(51)]]:
            with self.assertRaises(ValueError):
                self.engine.score("q", hits)
        self.assertEqual(self.model.calls, 0)

    def test_nonfinite_and_wrong_number_of_model_scores_fail(self):
        for values in [torch.tensor([[float("nan")]]), torch.zeros(2, 1)]:
            self.model.output = values
            with self.assertRaisesRegex(ValueError, "invalid relevance"):
                self.engine.score("q", [hit(0)])

    def test_raw_logits_stable_ties_preserve_metadata_and_original_scores(self):
        self.model.output = torch.tensor([[-2.0], [5.0], [5.0]])
        hits = [hit(i) for i in range(3)]
        original = copy.deepcopy(hits)
        result = self.engine.rerank("q", hits)
        self.assertEqual([r["candidate_rank"] for r in result], [2, 3, 1])
        self.assertEqual([r["score"] for r in result], [5, 5, -2])
        self.assertEqual(result[0]["retrieval_score"], 0.5)
        self.assertEqual(result[0]["score_kind"], "reranker_logit_difference")
        self.assertEqual(hits, original)


class SelectionTests(unittest.TestCase):
    def test_all_quality_and_latency_gates_are_required(self):
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
        self.assertTrue(select_enabled({"off": base, "on": summary(0.6)}, 15, PROFILE))
        for changed, seconds in [
            (summary(0.5), 1),
            (summary(0.6, 0.4), 1),
            (summary(0.6, docs=0.7), 1),
            (summary(0.6), 15.01),
        ]:
            self.assertFalse(
                select_enabled({"off": base, "on": changed}, seconds, PROFILE)
            )

    def test_reserve_guard_and_nonfinite_saved_scores(self):
        with self.assertRaisesRegex(ValueError, "Reserve"):
            evaluate(
                [{"split": "reserve"}], [[hit(i) for i in range(50)]], np.zeros((1, 50))
            )
        with self.assertRaisesRegex(ValueError, "matrix"):
            evaluate(
                [{"split": "dev"}],
                [[hit(i) for i in range(50)]],
                np.full((1, 50), np.nan),
            )


class RuntimeTests(unittest.TestCase):
    def test_frozen_window_and_zero_request(self):
        engine = RerankedSearch()
        engine.retrieval = Mock()
        engine.reranker = Mock()
        hits = [hit(i) for i in range(50)]
        engine.retrieval.search.return_value = hits
        engine.reranker.rerank.return_value = list(reversed(hits))
        self.assertEqual(engine.search("q", 2), hits[::-1][:2])
        engine.retrieval.search.assert_called_once_with("q", 50)
        engine.reranker.rerank.assert_called_once_with("q", hits)
        engine.retrieval.reset_mock()
        self.assertEqual(engine.search("q", 0), [])
        for k in [51, -1, True, 1.2]:
            with self.assertRaises(ValueError):
                engine.search("q", k)
        engine.retrieval.search.assert_not_called()

    def test_disabled_search_delegates_without_reranking(self):
        engine = RerankedSearch()
        engine.retrieval = Mock()
        engine.reranker = None
        engine.search("q", 3)
        engine.retrieval.search.assert_called_once_with("q", 3)

    def test_retriever_explicit_reranking_blocks_cosine_context_threshold(self):
        raw = Mock()
        raw.search.return_value = [hit(0)]
        with (
            patch("src.knowledge_base.retriever.VectorStore"),
            patch.object(RerankedSearch, "from_profile", return_value=raw),
        ):
            retriever = Retriever(reranker_profile="candidate.json")
            retriever.search("q", 10)
            raw.search.assert_called_once_with("q", 10)
            with self.assertRaisesRegex(ValueError, "raw-search only"):
                retriever.retrieve_relevant_context("q", min_score=0.5)
        with (
            patch("src.knowledge_base.retriever.VectorStore") as store,
            self.assertRaisesRegex(ValueError, "Choose one"),
        ):
            Retriever(retrieval_profile="g", reranker_profile="h")
        store.assert_not_called()

    def test_profile_verifies_hash_source_model_template_and_disabled_does_not_load(
        self,
    ):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            g = root / "g"
            g.mkdir()
            (g / "run.json").write_text("{}")
            model = {**PROFILE, "chat_template_sha256": "fixed"}
            (root / "model_profile.json").write_text(json.dumps(model))
            spec = {
                "schema": "chemqa-reranked-search-v1",
                "enabled": False,
                "candidate_window": 50,
                "score_policy": "raw_only_no_context_threshold",
                "model_profile": model,
                "retrieval_profile": str(g / "retrieval_profile.json"),
                "retrieval_run_sha256": sha256_file(g / "run.json"),
            }
            path = root / "reranker_profile.json"

            def publish(value):
                path.write_text(json.dumps(value))
                (root / "run.json").write_text(
                    json.dumps(
                        {
                            "schema": "chemqa-artifact-run-v1",
                            "kind": "rerank_runs",
                            "status": "ready",
                            "source_G_run_sha256": spec["retrieval_run_sha256"],
                            "files": {
                                p.name: sha256_file(p)
                                for p in [path, root / "model_profile.json"]
                            },
                        }
                    )
                )

            with (
                patch.object(
                    HybridSearch,
                    "from_profile",
                    return_value=SimpleNamespace(window=50),
                ),
                patch("src.knowledge_base.reranked_search.QwenReranker") as factory,
            ):
                publish(spec)
                self.assertIsNone(RerankedSearch.from_profile(Mock(), path).reranker)
                factory.assert_not_called()
                path.write_text(path.read_text() + " ")
                with self.assertRaisesRegex(ValueError, "verified"):
                    RerankedSearch.from_profile(Mock(), path)
                publish({**spec, "retrieval_run_sha256": "changed"})
                with self.assertRaisesRegex(ValueError, "source G"):
                    RerankedSearch.from_profile(Mock(), path)
                publish({**spec, "model_profile": {**model, "instruction": "changed"}})
                with self.assertRaisesRegex(ValueError, "model profile"):
                    RerankedSearch.from_profile(Mock(), path)
                publish({**spec, "enabled": True})
                factory.return_value.template_sha256 = "changed"
                with self.assertRaisesRegex(ValueError, "template changed"):
                    RerankedSearch.from_profile(Mock(), path)


if __name__ == "__main__":
    unittest.main()
