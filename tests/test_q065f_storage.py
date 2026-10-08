"""Storage corruption, exact retrieval, immutability and compatibility contracts."""

import copy
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import numpy as np

from config.settings import settings
from src.knowledge_base.binary_index import FILES, BinaryIndex, write_binary_index
from src.knowledge_base.identity import document_id, normalize_chunk
from src.knowledge_base.location import LOCATION_VERSION
from src.knowledge_base.similarity import cosine_scores, top_indices
from src.knowledge_base.vector_store import VectorStore
from src.utils.artifacts import sha256_file


def source_index():
    embedding = {
        "schema": "chemqa-embedding-profile-v1",
        "model": "synthetic",
        "revision": "a" * 40,
        "dimension": 3,
        "max_sequence_tokens": 32,
        "query_prompt": "find:",
        "document_prompt": "",
        "normalize_embeddings": True,
        "padding_side": "left",
        "precision_policy": "mps-fp16-cpu-fp32-v1",
        "token_count_includes_prompt_and_special_tokens": True,
    }
    documents = []
    for i, text in enumerate(["H₃O⁺ + HSO₄⁻", "表格 3: 0.25 V", "对照 α", "同分证据"]):
        documents.append(
            normalize_chunk(
                {
                    "source": "synthetic.pdf",
                    "doc_id": document_id(b"synthetic"),
                    "chunk_index": i,
                    "text": text,
                    "location_version": LOCATION_VERSION,
                    "location_status": "located",
                    "location_extractor": {"library": "synthetic"},
                    "page_numbers": [1],
                    "source_spans": [
                        {
                            "page_number": 1,
                            "char_start": 0,
                            "char_end": len(text),
                            "raw_text": text,
                        }
                    ],
                    "text_processing_version": "page-window-test",
                    "extra": {"aliases": ["名称", "alias"]},
                }
            )
        )
    return {
        "embedding": embedding,
        "documents": documents,
        "vectors": np.array(
            [[1, 0, 0], [0, 1, 0], [-1, 0, 0], [1, 0, 0]], dtype=np.float32
        ),
        "chunking": {
            "strategy": "page-window",
            "target_tokens": 32,
            "overlap_tokens": 4,
        },
        "corpus_sha256": "b" * 64,
    }


class BinaryStorageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name)
        self.source = source_index()
        write_binary_index(self.path, self.source, source={"test": True})
        self.publish()

    def publish(self, **extra):
        record = {
            "schema": "chemqa-artifact-run-v1",
            "kind": "indexes",
            "status": "ready",
            "storage_backend": "numpy-float32-sqlite",
            "files": {n: sha256_file(self.path / n) for n in FILES},
            **extra,
        }
        (self.path / "run.json").write_text(json.dumps(record))

    def load(self):
        index = BinaryIndex(self.path, expected_embedding=self.source["embedding"])
        self.addCleanup(index.close)
        return index

    def test_roundtrip_preserves_vectors_text_locations_and_extra_metadata(self):
        index = self.load()
        self.assertEqual(list(index.documents), self.source["documents"])
        np.testing.assert_array_equal(index.vectors, self.source["vectors"])
        self.assertFalse(index.vectors.flags.writeable)
        self.assertEqual(index.documents[-1], self.source["documents"][-1])
        self.assertEqual(index.documents[1:3], self.source["documents"][1:3])
        with self.assertRaises(IndexError):
            _ = index.documents[4]

    def test_active_torch_computation_coexists_with_binary_search(self):
        import torch

        matrix = torch.ones((32, 32))
        self.assertEqual(float((matrix @ matrix).sum()), 32768.0)
        hits = self.load().search(np.array([1, 0, 0]), 2)
        self.assertEqual([h["document"]["chunk_index"] for h in hits], [0, 3])

    def test_exact_cosine_order_and_boundary_ties_use_source_row_order(self):
        index = self.load()
        for query in [np.array([1, 0, 0]), np.array([2, 1, 0]), np.array([-3, 2, 1])]:
            scores = cosine_scores(self.source["vectors"], query)
            for count in [1, 2, 4, 20]:
                hits = index.search(query, count)
                rows = top_indices(scores, count)
                self.assertEqual(
                    [h["document"]["chunk_id"] for h in hits],
                    [self.source["documents"][i]["chunk_id"] for i in rows],
                )
                np.testing.assert_allclose(
                    [h["score"] for h in hits], scores[rows], atol=2e-6, rtol=0
                )

    def test_invalid_queries_counts_and_zero_request(self):
        index = self.load()
        self.assertEqual(index.search(None, 0), [])
        for query in [[0, 0, 0], [1, 0], [np.nan, 0, 1], [np.inf, 0, 1]]:
            with self.assertRaises(ValueError):
                index.search(query)
        for count in [-1, True, 1.5]:
            with self.assertRaises(ValueError):
                index.search([1, 0, 0], count)

    def test_profile_and_instruction_mismatch_rejected(self):
        for field, value in [
            ("revision", "b" * 40),
            ("query_prompt", "wrong"),
            ("dimension", 4),
            ("padding_side", "right"),
        ]:
            expected = {**self.source["embedding"], field: value}
            with self.assertRaises(ValueError):
                BinaryIndex(self.path, expected_embedding=expected)

    def test_unpublished_and_incomplete_candidates_rejected(self):
        self.publish(status="running")
        with self.assertRaisesRegex(ValueError, "ready"):
            self.load()
        self.publish(files={})
        with self.assertRaisesRegex(ValueError, "checksum"):
            self.load()
        (self.path / "run.json").unlink()
        with self.assertRaises(FileNotFoundError):
            self.load()

    def test_all_payload_files_checked_before_loading(self):
        for name in FILES:
            original = (self.path / name).read_bytes()
            (self.path / name).write_bytes(original + b"changed")
            with self.assertRaisesRegex(ValueError, "checksum"):
                self.load()
            (self.path / name).write_bytes(original)

    def test_row_permutation_detected_even_with_recomputed_file_checksum(self):
        with sqlite3.connect(self.path / "metadata.sqlite3") as connection:
            connection.execute("UPDATE chunks SET row_id=99 WHERE row_id=0")
        self.publish()
        with self.assertRaisesRegex(ValueError, "mapping"):
            self.load()

    def test_payload_change_detected_even_with_recomputed_file_checksum(self):
        with sqlite3.connect(self.path / "metadata.sqlite3") as connection:
            doc = copy.deepcopy(self.source["documents"][0])
            doc["extra"]["aliases"] = ["changed"]
            connection.execute(
                "UPDATE chunks SET payload=? WHERE row_id=0", (json.dumps(doc),)
            )
        self.publish()
        with self.assertRaisesRegex(ValueError, "content"):
            self.load()

    def test_vector_content_change_detected_with_recomputed_file_checksum(self):
        altered = self.source["vectors"].copy()
        altered[0] = [0, 0, 1]
        np.save(self.path / "vectors.npy", altered, allow_pickle=False)
        self.publish()
        with self.assertRaisesRegex(ValueError, "content"):
            self.load()

    def test_binary_dimension_count_dtype_and_object_arrays_rejected(self):
        for vectors in [
            self.source["vectors"][:3],
            np.eye(4, dtype=np.float32),
            self.source["vectors"].astype(np.float64),
            np.array([object()], dtype=object),
        ]:
            np.save(self.path / "vectors.npy", vectors)
            self.publish()
            with self.assertRaises(ValueError):
                self.load()

    def test_published_metadata_is_read_only_and_writer_refuses_overwrite(self):
        index = self.load()
        with self.assertRaises(sqlite3.OperationalError):
            index.connection.execute("DELETE FROM chunks")
        with self.assertRaisesRegex(ValueError, "overwrite"):
            write_binary_index(self.path, self.source, source={})

    def test_writer_rejects_duplicate_identity_invalid_vectors_and_empty_input(self):
        for changed in [
            {"documents": [], "vectors": np.empty((0, 3), dtype=np.float32)},
            {"vectors": np.ones((4, 3), dtype=np.float32)},
            {"vectors": np.array([[np.nan, 0, 0]] * 4, dtype=np.float32)},
            {"documents": [self.source["documents"][0]] * 4},
        ]:
            with (
                tempfile.TemporaryDirectory() as directory,
                self.assertRaises((ValueError, sqlite3.IntegrityError)),
            ):
                write_binary_index(
                    Path(directory), {**self.source, **changed}, source={}
                )

    def test_writer_rejects_lossy_conversion_of_float64_vectors(self):
        vectors = self.source["vectors"].astype(np.float64)
        vectors[0] = [np.sqrt(0.5), np.sqrt(0.5), 0]
        with (
            tempfile.TemporaryDirectory() as directory,
            self.assertRaisesRegex(ValueError, "change source values"),
        ):
            write_binary_index(
                Path(directory), {**self.source, "vectors": vectors}, source={}
            )

    def test_vector_store_selects_binary_and_query_encoding_branch(self):
        with patch.object(settings, "VECTOR_DB_DIR", str(self.path)):
            store = VectorStore.__new__(VectorStore)
            store.encoder = Mock()
            store.encoder.manifest.return_value = self.source["embedding"]
            store.encoder.encode.return_value = np.array([1, 0, 0])
            store.vector_index = store._load_vector_index()
            self.addCleanup(store.storage.close)
            hits = store.similarity_search("query", 2)
            store.encoder.encode.assert_called_once_with("query", kind="query")
            self.assertEqual([h["document"]["chunk_index"] for h in hits], [0, 3])
            with self.assertRaisesRegex(ValueError, "immutable"):
                store.add_documents([])

    def test_binary_requires_explicit_encoder_and_never_falls_back_to_json(self):
        with patch.object(settings, "VECTOR_DB_DIR", str(self.path)):
            store = VectorStore.__new__(VectorStore)
            with self.assertRaisesRegex(ValueError, "explicit"):
                store._load_vector_index()
            store.encoder = SimpleNamespace(manifest=lambda: self.source["embedding"])
            self.publish(status="running")
            with self.assertRaisesRegex(ValueError, "ready"):
                store._load_vector_index()


if __name__ == "__main__":
    unittest.main()
