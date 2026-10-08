"""Prompt budgets, untruncated inputs, source coverage and controlled selection."""

import copy
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import numpy as np

from config.settings import settings
from scripts.validate_q065e import (
    RESOURCE_COUNTERS,
    encode_batches,
    evaluate,
    selected_variant,
)
from src.knowledge_base.embedding import CandidateEncoder, profile_from_file
from src.knowledge_base.identity import document_id
from src.knowledge_base.location import clean_with_offsets
from src.knowledge_base.paragraph_processor import ParagraphProcessor
from src.knowledge_base.retriever import Retriever
from src.knowledge_base.vector_store import VectorStore
from src.pipeline.vector_index_builder import VectorIndexBuilder
from src.utils.artifacts import config_record
from tests.test_q02_location import page_document
from tests.test_q03_text_processing import CharacterTokenizer


class FullTokenizer(CharacterTokenizer):
    padding_side = "left"

    def __call__(self, text, **kwargs):
        if isinstance(text, list):
            return {"input_ids": [self(t, **kwargs)["input_ids"] for t in text]}
        result = super().__call__(text, **kwargs)
        if kwargs.get("add_special_tokens", True):
            result["input_ids"] = [101, *result["input_ids"], 102]
        return result


class EncoderModel:
    def __init__(self, *, truncate=False):
        self.tokenizer = FullTokenizer()
        self.max_seq_length = 128
        self.truncate = truncate
        self.encode = Mock(
            side_effect=lambda texts, **kw: np.asarray([[1, 2, 3]] * len(texts))
        )

    def get_embedding_dimension(self):
        return 3

    def preprocess(self, texts):
        rows = self.tokenizer(texts, add_special_tokens=True)["input_ids"]
        if self.truncate:
            rows = [r[:-1] for r in rows]
        width = max(map(len, rows))
        return {
            "input_ids": np.asarray([[0] * (width - len(r)) + r for r in rows]),
            "attention_mask": np.asarray(
                [[0] * (width - len(r)) + [1] * len(r) for r in rows]
            ),
        }


def profile():
    p, _ = profile_from_file(
        Path(__file__).resolve().parents[1] / "config/q065e_embedding.json"
    )
    return {
        **p,
        "dimension": 3,
        "max_sequence_tokens": 32,
        "query_prompt": "Instruct: find\nQuery:",
    }


class CandidateEmbeddingTests(unittest.TestCase):
    def test_query_prompt_and_special_tokens_are_budgeted_once(self):
        model = EncoderModel()
        encoder = CandidateEncoder(profile(), model=model)
        doc = "HSO₄−"
        self.assertGreater(encoder.count(doc, "query"), encoder.count(doc))
        encoder.encode([doc], kind="query")
        args, kwargs = model.encode.call_args
        self.assertEqual(args[0], [profile()["query_prompt"] + doc])
        self.assertEqual(kwargs["prompt"], "")
        self.assertTrue(kwargs["normalize_embeddings"])

    def test_oversized_prompted_query_fails_before_encoding(self):
        model = EncoderModel()
        encoder = CandidateEncoder(profile(), model=model)
        with self.assertRaisesRegex(ValueError, "including prompt"):
            encoder.encode(["x" * 30], kind="query")
        model.encode.assert_not_called()
        self.assertEqual(encoder.encode(["x" * 30]).shape, (1, 3))

    def test_actual_tokenizer_truncation_is_detected(self):
        model = EncoderModel(truncate=True)
        encoder = CandidateEncoder(profile(), model=model)
        with self.assertRaisesRegex(ValueError, "truncate or alter"):
            encoder.encode(["condition"])
        model.encode.assert_not_called()

    def test_profile_overrides_and_unpinned_revision_rejected(self):
        p = profile()
        with self.assertRaises(ValueError):
            CandidateEncoder({**p, "revision": "main"}, model=EncoderModel())
        encoder = CandidateEncoder(p, model=EncoderModel())
        for override in [
            {"prompt": "wrong"},
            {"truncate_dim": 2},
            {"precision": "int8"},
        ]:
            with self.assertRaises(ValueError):
                encoder.encode(["text"], **override)

    def test_invalid_and_zero_vectors_are_rejected(self):
        for values in [[[0, 0, 0]], [[float("nan"), 1, 2]], [[1, 2]]]:
            model = EncoderModel()
            model.encode.return_value = values
            model.encode.side_effect = None
            encoder = CandidateEncoder(profile(), model=model)
            with self.assertRaises(ValueError):
                encoder.encode(["text"])

    def test_profile_manifest_carries_instruction_and_normalization(self):
        p = profile()
        encoder = CandidateEncoder(p, model=EncoderModel())
        p["query_prompt"] = "mutated"
        self.assertNotEqual(encoder.manifest()["query_prompt"], "mutated")
        vectors = encoder.encode(["text", "other"])
        np.testing.assert_allclose(np.linalg.norm(vectors, axis=1), 1, atol=1e-6)


class ParagraphChunkTests(unittest.TestCase):
    def processor(self, target=20, overlap=3, blocks=True):
        return ParagraphProcessor(
            SimpleNamespace(limit=64, tokenizer=CharacterTokenizer()),
            target_tokens=target,
            overlap_tokens=overlap,
            use_blocks=blocks,
        )

    def test_block_boundary_preferred_over_midparagraph_cut(self):
        doc = page_document(["abcde fghij\nklmno pqrst\nuvwxy zabcd\n"])
        doc["paragraph_ends"] = [12, 24, len(doc["text"])]
        block = self.processor(overlap=0).process_document(doc)
        window = self.processor(overlap=0, blocks=False).process_document(doc)
        self.assertEqual(block[0]["text"], "abcde fghij")
        self.assertNotEqual(block[0]["text"], window[0]["text"])

    def test_long_multilingual_tokens_preserve_all_source_characters(self):
        doc = page_document(
            ["甲乙丙丁" * 20 + " HSO₄− + 25 °C\n", "[Ni(CN)₄]²⁻ " + "a" * 70 + "\n"]
        )
        doc["paragraph_ends"] = [p["char_end"] for p in doc["pages"]]
        processor = self.processor()
        chunks = processor.process_document(doc)
        covered = set()
        for chunk in chunks:
            self.assertEqual(len(chunk["page_numbers"]), 1)
            self.assertLessEqual(chunk["embedding_token_count"], 20)
            for span in chunk["source_spans"]:
                page = doc["pages"][span["page_number"] - 1]
                self.assertEqual(
                    page["text"][span["char_start"] : span["char_end"]],
                    span["raw_text"],
                )
                covered.update(
                    range(
                        page["char_start"] + span["char_start"],
                        page["char_start"] + span["char_end"],
                    )
                )
            reconstructed = clean_with_offsets(
                "".join(s["raw_text"] for s in chunk["source_spans"]),
                preserve_symbols=True,
            )[0]
            self.assertEqual(reconstructed, chunk["text"])
        self.assertTrue(
            all(i in covered for i, c in enumerate(doc["text"]) if not c.isspace())
        )

    def test_empty_pages_and_invalid_overlap(self):
        doc = page_document(["", " \n", "abc def\n", ""])
        self.assertEqual(self.processor().process_document(doc)[0]["page_numbers"], [3])
        for overlap in [-1, 18, 20]:
            with self.assertRaises(ValueError):
                self.processor(overlap=overlap)

    def test_pilot_gate_rejects_regression_and_prefers_complete_anchors(self):
        variants = [
            {"name": "short", "strategy": "page-block"},
            {"name": "long", "strategy": "page-block"},
        ]

        def row(recall, coverage, count):
            return {
                "summary": {
                    "at_k": {
                        "5": {"mean_anchor_character_coverage": coverage},
                        "10": {
                            "complete_anchor_recall": recall,
                            "mean_anchor_character_coverage": coverage,
                        },
                    }
                },
                "chunk_count": count,
            }

        results = {
            "minilm-old-chunks": row(0.5, 0.6, 100),
            "short": row(0.5, 0.9, 40),
            "long": row(0.8, 0.8, 50),
        }
        self.assertEqual(selected_variant(results, variants)["name"], "long")
        bad = copy.deepcopy(results)
        bad["minilm-old-chunks"] = row(0.9, 0.9, 100)
        with self.assertRaises(ValueError):
            selected_variant(bad, variants)

    def test_reserve_queries_are_not_ranked(self):
        with self.assertRaisesRegex(ValueError, "Reserve"):
            evaluate([{"split": "reserve"}], [], np.empty((0, 3)), np.ones((1, 3)))


class CandidateIntegrationTests(unittest.TestCase):
    def test_query_scoring_uses_query_encoder_branch(self):
        store = VectorStore.__new__(VectorStore)
        store.encoder = Mock()
        store.encoder.encode.return_value = np.array([1, 0, 0])
        store.vector_index = {"documents": [{}, {}], "vectors": [[1, 0, 0], [0, 1, 0]]}
        np.testing.assert_allclose(store.score_query("question"), [1, 0])
        store.encoder.encode.assert_called_once_with("question", kind="query")

    def test_candidate_index_rejects_wrong_profile_dimensions_or_norm(self):
        encoder = CandidateEncoder(profile(), model=EncoderModel())
        record = {
            "source": "synthetic.pdf",
            "doc_id": document_id(b"synthetic PDF"),
            "chunk_index": 0,
            "text": "text",
        }
        with (
            tempfile.TemporaryDirectory() as directory,
            patch.object(settings, "VECTOR_DB_DIR", directory),
        ):
            store = VectorStore.__new__(VectorStore)
            store.encoder = store.budget = encoder
            base = {
                "documents": [record],
                "vectors": [[1, 0, 0]],
                "embedding": encoder.manifest(),
            }
            for changed in [
                {"embedding": {**encoder.manifest(), "query_prompt": "different"}},
                {"vectors": [[1, 0]]},
                {"vectors": [[2, 0, 0]]},
                {"embedding": None},
            ]:
                Path(directory, "vector_index.json").write_text(
                    json.dumps({**base, **changed})
                )
                with self.assertRaises(ValueError):
                    store._load_vector_index()
            Path(directory, "vector_index.json").write_text(json.dumps(base))
            self.assertEqual(store._load_vector_index()["vectors"].shape, (1, 3))

    def test_old_threshold_is_not_implicitly_applied_to_candidate(self):
        retriever = Retriever.__new__(Retriever)
        retriever.vector_store = Mock()
        retriever.vector_store.similarity_search.return_value = []
        with patch.object(settings, "EMBEDDING_PROFILE", "candidate.json"):
            with self.assertRaisesRegex(ValueError, "uncalibrated"):
                retriever.retrieve_relevant_context("question")
            retriever.vector_store.similarity_search.assert_not_called()
            self.assertEqual(
                retriever.retrieve_relevant_context(
                    "question", min_score=0, return_dict_list=True
                ),
                [],
            )

    def test_legacy_builder_does_not_silently_use_wrong_candidate_chunking(self):
        with (
            patch.object(settings, "EMBEDDING_PROFILE", "candidate.json"),
            patch("src.pipeline.vector_index_builder.VectorStore") as store,
        ):
            with self.assertRaisesRegex(ValueError, "scripts.validate_q065e"):
                VectorIndexBuilder()
            store.assert_not_called()

    def test_config_snapshot_records_effective_candidate_model(self):
        path = str(Path(__file__).resolve().parents[1] / "config/q065e_embedding.json")
        with patch.object(settings, "EMBEDDING_PROFILE", path):
            record = config_record()
        self.assertEqual(record["embedding_model"], "Qwen/Qwen3-Embedding-0.6B")
        self.assertEqual(record["embedding_profile"], path)


class LongRunResourceTests(unittest.TestCase):
    def encoder(self):
        encoder = Mock()
        encoder.model.device = "mps:0"
        encoder.encode.side_effect = lambda texts, **kw: np.ones(
            (len(texts), 3), dtype=np.float32
        )
        return encoder

    def test_unused_mps_cache_released_between_outer_batches(self):
        with (
            patch(
                "torch.mps.driver_allocated_memory",
                side_effect=[4 * 1024**3, 1024**3, 5 * 1024**3, 2 * 1024**3],
            ),
            patch("torch.mps.empty_cache") as release,
            patch.dict(
                RESOURCE_COUNTERS,
                {
                    "mps_driver_max_sampled_bytes": 0,
                    "mps_driver_max_after_cache_clear_bytes": 0,
                },
            ),
        ):
            vectors, _ = encode_batches(self.encoder(), ["text"] * 65, "document", 8)
            self.assertEqual(vectors.shape, (65, 3))
            self.assertEqual(release.call_count, 2)
            self.assertEqual(
                RESOURCE_COUNTERS["mps_driver_max_sampled_bytes"], 5 * 1024**3
            )

    def test_persistent_resource_excess_aborts_before_publication(self):
        with (
            patch("torch.mps.driver_allocated_memory", return_value=7 * 1024**3),
            patch("torch.mps.empty_cache"),
            patch.dict(
                RESOURCE_COUNTERS,
                {
                    "mps_driver_max_sampled_bytes": 0,
                    "mps_driver_max_after_cache_clear_bytes": 0,
                },
            ),
            self.assertRaisesRegex(RuntimeError, "above 6 GiB"),
        ):
            encode_batches(self.encoder(), ["text"], "document", 8)


if __name__ == "__main__":
    unittest.main()
