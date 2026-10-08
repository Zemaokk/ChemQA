"""Regression checks for identity collisions, duplicate imports and citation tracing."""

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import numpy as np
import pymupdf

from config.prompts import ORGANIC_ELECTROCATALYSIS_PROMPT
from scripts.migrate_q01 import migrate
from src.api_integration.result import GenerationResult
from src.knowledge_base.identity import chunk_id, document_id, normalize_chunk
from src.knowledge_base.pdf_loader import PDFLoader
from src.knowledge_base.retriever import Retriever
from src.knowledge_base.text_processor import TextProcessor
from src.knowledge_base.vector_store import VectorStore
from src.pipeline.vector_index_builder import VectorIndexBuilder
from src.qa_system.citation_analyzer import CitationAnalyzer
from src.qa_system.expert_system import ChemicalQAExpert
from src.qa_system.response_formatter import ResponseFormatter


def identified(source: str, content: bytes, text: str, index: int = 0) -> dict:
    return normalize_chunk(
        {
            "source": source,
            "doc_id": document_id(content),
            "text": text,
            "chunk_index": index,
        }
    )


class IdentityTests(unittest.TestCase):
    def setUp(self):
        self.a = identified("A.pdf", b"PDF A", "A evidence")
        self.b = identified("B.pdf", b"PDF B", "B evidence")
        self.context = [self.a, self.b]

    def test_same_local_index_has_distinct_chunk_ids_and_citations(self):
        answer = (
            f"A claim [Ref {self.a['chunk_id']}] B claim [Ref {self.b['chunk_id']}]"
        )
        self.assertNotEqual(self.a["chunk_id"], self.b["chunk_id"])
        result = ResponseFormatter().format_answer(answer, self.context)
        self.assertEqual(result["formatted_answer"], "A claim [1] B claim [2]")
        report = CitationAnalyzer().analyze_citations(answer, self.context)
        self.assertEqual(len(report["cited_chunks_analysis"]["chunk_mapping"]), 2)
        self.assertEqual(report["citation_coverage"]["cited_count"], 2)

    def test_ambiguous_local_number_is_not_assigned_to_either_paper(self):
        answer = "Claim [Ref 0]"
        result = ResponseFormatter().format_answer(answer, self.context)
        self.assertIn("未解析引用", result["formatted_answer"])
        report = CitationAnalyzer().analyze_citations(answer, self.context)
        self.assertEqual(report["citation_coverage"]["cited_count"], 0)
        self.assertEqual(report["unresolved_citations"][0]["reason"], "ambiguous")

    def test_unknown_citation_remains_visible_and_unmapped(self):
        answer = "Claim [Ref nonexistent]"
        result = ResponseFormatter().format_answer(answer, self.context)
        self.assertIn("[Ref nonexistent]", result["formatted_answer"])
        self.assertEqual(result["unresolved_citations"][0]["reason"], "unknown")

    def test_document_source_cannot_be_counted_as_every_chunk(self):
        other = identified("A.pdf", b"PDF A", "Another A chunk", 1)
        report = CitationAnalyzer().analyze_citations("[Ref A.pdf]", [self.a, other])
        self.assertEqual(report["citation_coverage"]["cited_count"], 0)
        self.assertEqual(report["unresolved_citations"][0]["reason"], "ambiguous")

    def test_duplicate_aliases_share_identity_and_reference_number(self):
        copied = identified("A copy.pdf", b"PDF A", "A evidence")
        result = ResponseFormatter().format_answer(
            f"[Ref {self.a['chunk_id']}]", [self.a, copied]
        )
        self.assertEqual(result["num_references"], 1)
        self.assertEqual(len(result["evidence_map"]), 1)
        self.assertEqual(result["evidence_map"][0]["sources"], ["A copy.pdf", "A.pdf"])

    def test_nested_chunk_metadata_survives_and_tampering_is_rejected(self):
        nested = {
            "text": self.a["text"],
            "metadata": {k: v for k, v in self.a.items() if k != "text"},
        }
        self.assertEqual(normalize_chunk(nested)["chunk_id"], self.a["chunk_id"])
        with self.assertRaises(ValueError):
            normalize_chunk({**self.a, "text": "changed text"})
        with self.assertRaises(ValueError):
            normalize_chunk({**nested, "doc_id": self.b["doc_id"]})
        self.assertNotEqual(
            chunk_id(self.a["doc_id"], 0, "changed text"), self.a["chunk_id"]
        )

    def test_incremental_import_does_not_encode_duplicate_chunks(self):
        store = VectorStore.__new__(VectorStore)
        store.vector_index = {
            "documents": [dict(self.a)],
            "vectors": np.array([[1.0, 0.0]]),
        }
        store.model = Mock()
        store.model.encode.return_value = np.array([[0.0, 1.0]])
        store._save_vector_index = Mock()
        store.add_documents([self.a, self.a, self.b, self.b])
        self.assertEqual(len(store.vector_index["documents"]), 2)
        store.model.encode.assert_called_once_with([self.b["text"]])
        store.add_documents([self.a, self.b])
        self.assertEqual(len(store.vector_index["documents"]), 2)
        self.assertEqual(store.model.encode.call_count, 1)

    def test_retrieval_and_string_context_keep_stable_identity(self):
        store = VectorStore.__new__(VectorStore)
        store.vector_index = {"documents": self.context, "vectors": np.eye(2)}
        store.model = Mock()
        store.model.encode.return_value = np.array([1.0, 0.0])
        result = store.similarity_search("query", 1)[0]["document"]
        self.assertEqual(result["chunk_id"], self.a["chunk_id"])
        retriever = Retriever.__new__(Retriever)
        retriever.vector_store = store
        text = retriever.retrieve_relevant_context("query", top_k=1)
        self.assertIn(f"[Ref {self.a['chunk_id']}]", text)

    def test_answer_record_preserves_exact_chunk_and_raw_citation(self):
        expert = ChemicalQAExpert.__new__(ChemicalQAExpert)
        expert.retriever = Mock()
        expert.retriever.retrieve_relevant_context.return_value = self.context
        expert.generator = Mock(
            prompt_template=ORGANIC_ELECTROCATALYSIS_PROMPT, last_validation=None
        )
        expert.generator.generate_answer_result.return_value = GenerationResult(
            status="success",
            content=f"A claim [Ref {self.a['chunk_id']}]",
            request_sent=True,
            attempts=1,
        )
        expert.formatter = ResponseFormatter()
        with tempfile.TemporaryDirectory() as folder:
            with patch("src.utils.artifacts.settings.OUTPUT_DIR", folder):
                answer = expert.answer_query("Question", analyze_citations=False)
            record = json.loads(
                (expert.last_run_dir / "answer.evidence.json").read_text()
            )
            self.assertIn(self.a["chunk_id"], answer)
            self.assertEqual(record["evidence_map"][0]["text"], self.a["text"])
            self.assertIn(self.a["chunk_id"], record["raw_answer"])

    def test_rebuild_deduplicates_before_encoding(self):
        builder = VectorIndexBuilder.__new__(VectorIndexBuilder)
        builder.vector_store = Mock()
        builder.vector_store.encode_texts.return_value = np.array([[1.0, 0.0]])
        builder.vector_store.budget.manifest.return_value = {}
        with tempfile.TemporaryDirectory() as folder:
            with patch(
                "src.pipeline.vector_index_builder.settings.VECTOR_DB_DIR", folder
            ):
                builder.build_index([self.a, self.a], output_dir=folder)
            saved = json.loads((Path(folder) / "vector_index.json").read_text())
        self.assertEqual(len(saved["documents"]), 1)
        self.assertEqual(builder.vector_store.encode_texts.call_count, 1)

    def test_legacy_load_never_invents_text_or_rewrites_disk(self):
        store = VectorStore.__new__(VectorStore)
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "vector_index.json"
            path.write_text(json.dumps({"legacy.pdf_0": [1, 0]}))
            before = path.read_bytes()
            with (
                patch("src.knowledge_base.vector_store.settings.VECTOR_DB_DIR", folder),
                self.assertRaises(ValueError),
            ):
                store._load_vector_index()
            self.assertEqual(path.read_bytes(), before)

    def test_pdf_rename_and_legacy_migration_are_idempotent(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / "paper.pdf"
            with pymupdf.open() as pdf:
                pdf.new_page().insert_text((40, 40), "Evidence from a synthetic PDF.")
                pdf.save(source)
            copied = Path(folder) / "renamed.pdf"
            copied.write_bytes(source.read_bytes())
            loader = PDFLoader(folder)
            a, b = loader.load_pdf(str(source))[0], loader.load_pdf(str(copied))[0]
            self.assertEqual(a["metadata"]["doc_id"], b["metadata"]["doc_id"])
            new_chunks = TextProcessor(legacy=True).process_document(a)
            self.assertIn("chunk_id", new_chunks[0]["metadata"])
            chunks = [
                {"text": "evidence", "metadata": {"source": str(p), "chunk_index": 0}}
                for p in (source, copied)
            ]
            docs = [{"text": c["text"], **c["metadata"]} for c in chunks]
            old_index = {"documents": docs, "vectors": [[1.0, 0.0], [1.0, 0.0]]}
            migrated, index, report = migrate(chunks, old_index)
            self.assertEqual(report["duplicate_rows_removed"], 1)
            self.assertEqual(index["vectors"], [[1.0, 0.0]])
            repeated, repeated_index, _ = migrate(migrated, index)
            self.assertEqual(repeated, migrated)
            self.assertEqual(repeated_index, index)
            with self.assertRaises(ValueError):
                migrate(chunks, {**old_index, "vectors": [[1.0, 0.0], [0.0, 1.0]]})
            with self.assertRaises(ValueError):
                migrate(chunks, {**old_index, "vectors": [[1.0, 0.0]]})


if __name__ == "__main__":
    unittest.main()
