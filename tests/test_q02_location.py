"""Regression checks for physical PDF pages and exact extracted-text intervals."""

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import numpy as np
import pymupdf

from config.prompts import ORGANIC_ELECTROCATALYSIS_PROMPT
from scripts.migrate_q02 import migrate
from scripts.validate_q02 import validate
from src.api_integration.result import GenerationResult
from src.knowledge_base.identity import document_id, normalize_chunk, unique_chunks
from src.knowledge_base.location import (
    clean_with_offsets,
    validate_location,
)
from src.knowledge_base.pdf_loader import PDFLoader
from src.knowledge_base.retriever import Retriever
from src.knowledge_base.text_processor import TextProcessor
from src.knowledge_base.vector_store import VectorStore
from src.qa_system.citation_analyzer import CitationAnalyzer
from src.qa_system.expert_system import ChemicalQAExpert
from src.qa_system.response_formatter import ResponseFormatter


def page_document(texts: list[str]) -> dict:
    cursor = 0
    pages = []
    for number, text in enumerate(texts, 1):
        pages.append(
            {
                "page_number": number,
                "char_start": cursor,
                "char_end": cursor + len(text),
                "text": text,
            }
        )
        cursor += len(text)
    return {
        "text": "".join(texts),
        "pages": pages,
        "metadata": {
            "source": "synthetic.pdf",
            "doc_id": document_id(b"synthetic PDF"),
            "total_pages": len(texts),
        },
    }


class LocationTests(unittest.TestCase):
    def setUp(self):
        self.processor = TextProcessor(legacy=True)
        self.processor.chunk_size = 4
        self.processor.chunk_overlap = 1

    def test_clean_mapping_matches_existing_cleanup_with_unicode_and_symbols(self):
        raw = " \t(Ni2+)\r\nHSO4−  a @ b\n中文 μm / []  "
        cleaned, offsets = clean_with_offsets(raw)
        self.assertEqual(cleaned, self.processor.clean_text(raw))
        self.assertEqual(len(cleaned), len(offsets))
        for char, (start, end) in zip(cleaned, offsets, strict=True):
            self.assertEqual(char, " " if raw[start:end].isspace() else raw[start:end])

    def test_cross_page_overlap_keeps_exact_source_intervals_and_chunk_text(self):
        doc = page_document(
            ["one two three\n", "four five six\n", "seven eight nine\n"]
        )
        chunks = self.processor.process_document(doc)
        old_texts = self.processor.split_text(self.processor.clean_text(doc["text"]))
        self.assertEqual([c["text"] for c in chunks], old_texts)
        self.assertEqual(chunks[0]["metadata"]["page_numbers"], [1, 2])
        self.assertEqual(chunks[1]["metadata"]["page_numbers"], [2, 3])
        for chunk in chunks:
            for span in chunk["metadata"]["source_spans"]:
                page = doc["pages"][span["page_number"] - 1]
                self.assertEqual(
                    span["raw_text"],
                    page["text"][span["char_start"] : span["char_end"]],
                )
            raw = "".join(s["raw_text"] for s in chunk["metadata"]["source_spans"])
            self.assertEqual(
                " ".join(self.processor.clean_text(raw).split()), chunk["text"]
            )

    def test_blank_page_keeps_physical_page_number_without_inventing_evidence(self):
        doc = page_document(["one two\n", "", "three four\n"])
        chunk = self.processor.process_document(doc)[0]
        self.assertEqual(chunk["metadata"]["page_numbers"], [1, 3])
        self.assertNotIn(2, chunk["metadata"]["page_numbers"])

    def test_page_boundary_without_whitespace_preserves_old_joining_behavior(self):
        doc = page_document(["joined", "word second\n"])
        chunk = self.processor.process_document(doc)[0]
        self.assertEqual(chunk["text"], "joinedword second")
        self.assertEqual(chunk["metadata"]["page_numbers"], [1, 2])

    def test_removed_chemical_symbols_are_present_in_raw_excerpt(self):
        doc = page_document(["(Ni2+) and HSO4−\n"])
        chunk = self.processor.process_document(doc)[0]
        self.assertEqual(chunk["text"], "Ni2 and HSO4")
        raw = chunk["metadata"]["source_spans"][0]["raw_text"]
        self.assertEqual(raw, "(Ni2+) and HSO4−")

    def test_no_pages_is_explicitly_unavailable_and_invalid_boundaries_fail(self):
        doc = page_document(["evidence here\n"])
        doc.pop("pages")
        chunk = self.processor.process_document(doc)[0]
        self.assertEqual(chunk["metadata"]["location_status"], "unavailable")
        self.assertEqual(chunk["metadata"]["source_spans"], [])
        invalid = page_document(["evidence here\n"])
        invalid["pages"][0]["char_start"] = 1
        with self.assertRaises(ValueError):
            self.processor.process_document(invalid)

    def test_malformed_location_metadata_is_rejected(self):
        chunk = normalize_chunk(
            self.processor.process_document(page_document(["one two\n"]))[0]
        )
        bad = {**chunk, "source_spans": [{**chunk["source_spans"][0], "char_end": 999}]}
        with self.assertRaises(ValueError):
            normalize_chunk(bad)
        bad = {**chunk, "page_numbers": [99]}
        with self.assertRaises(ValueError):
            validate_location(bad)

    def test_repeated_import_upgrades_location_without_reencoding(self):
        located = normalize_chunk(
            self.processor.process_document(page_document(["one two\n"]))[0]
        )
        legacy = {
            k: v
            for k, v in located.items()
            if not k.startswith("location_")
            and k not in ("page_numbers", "source_spans")
        }
        merged = unique_chunks([legacy, located])[0]
        self.assertEqual(merged["source_spans"], located["source_spans"])
        store = VectorStore.__new__(VectorStore)
        store.vector_index = {"documents": [legacy], "vectors": np.array([[1.0, 0.0]])}
        store.model = Mock()
        store._save_vector_index = Mock()
        store.add_documents([located])
        store.model.encode.assert_not_called()
        self.assertEqual(store.vector_index["documents"][0]["page_numbers"], [1])
        conflicting = {
            **located,
            "source_spans": [
                {
                    **located["source_spans"][0],
                    "char_start": 1,
                    "char_end": len(located["source_spans"][0]["raw_text"]) + 1,
                }
            ],
        }
        with self.assertRaises(ValueError):
            unique_chunks([located, conflicting])

    def test_pdf_loader_preserves_blank_pages_and_document_text(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "three-pages.pdf"
            with pymupdf.open() as pdf:
                pdf.new_page().insert_text((40, 40), "first page")
                pdf.new_page()
                pdf.new_page().insert_text((40, 40), "third page")
                pdf.save(path)
            doc = PDFLoader().load_pdf(str(path))[0]
            self.assertEqual(len(doc["pages"]), 3)
            self.assertEqual(doc["pages"][1]["text"], "")
            self.assertEqual(doc["text"], "".join(p["text"] for p in doc["pages"]))
            self.assertEqual(doc["metadata"]["doc_id"], document_id(path.read_bytes()))

    def test_migration_keeps_ids_and_vectors_and_marks_nonmatching_text(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "paper.pdf"
            with pymupdf.open() as pdf:
                pdf.new_page().insert_text((40, 40), "real evidence here")
                pdf.save(path)
            base = {
                "source": str(path),
                "doc_id": document_id(path.read_bytes()),
                "chunk_index": 0,
            }
            good = normalize_chunk({**base, "text": "real evidence here"})
            bad = normalize_chunk({**base, "text": "historical different extraction"})
            processed = [
                {
                    "text": d["text"],
                    "metadata": {k: v for k, v in d.items() if k != "text"},
                }
                for d in (good, bad)
            ]
            index = {"documents": [good, bad], "vectors": [[1.0, 0.0], [0.0, 1.0]]}
            chunks, migrated, report = migrate(processed, index)
            self.assertEqual(report["located"], 1)
            self.assertEqual(report["unavailable"], 1)
            self.assertEqual(migrated["vectors"], index["vectors"])
            audit = validate(migrated, chunks, index)
            self.assertEqual(audit["verified_spans"], 1)
            corrupted = json.loads(json.dumps(migrated))
            corrupted["documents"][0]["source_spans"][0]["raw_text"] = "x" * len(
                corrupted["documents"][0]["source_spans"][0]["raw_text"]
            )
            corrupted_chunks = json.loads(json.dumps(chunks))
            corrupted_chunks[0]["metadata"]["source_spans"] = corrupted["documents"][0][
                "source_spans"
            ]
            with self.assertRaises(ValueError):
                validate(corrupted, corrupted_chunks, index)
            self.assertEqual(
                [d["chunk_id"] for d in migrated["documents"]],
                [good["chunk_id"], bad["chunk_id"]],
            )
            self.assertEqual(chunks[1]["metadata"]["source_spans"], [])
            again, repeated, _ = migrate(chunks, migrated)
            self.assertEqual(again, chunks)
            self.assertEqual(repeated, migrated)
            path.write_bytes(b"changed PDF bytes")
            with patch("scripts.migrate_q02.PDFLoader.load_pdf", return_value=[]):
                _, changed, _ = migrate(processed, index)
            self.assertTrue(
                all(d["location_status"] == "unavailable" for d in changed["documents"])
            )

    def test_location_survives_retrieval_citation_mapping_and_saved_answer(self):
        chunks = self.processor.process_document(
            page_document(["one two three\n", "four five six\n"])
        )
        doc = normalize_chunk(chunks[0])
        store = VectorStore.__new__(VectorStore)
        store.vector_index = {"documents": [doc], "vectors": np.array([[1.0, 0.0]])}
        store.model = Mock()
        store.model.encode.return_value = np.array([1.0, 0.0])
        retriever = Retriever.__new__(Retriever)
        retriever.vector_store = store
        context = retriever.retrieve_relevant_context(
            "query", top_k=1, return_dict_list=True
        )
        answer = f"Synthetic claim [Ref {doc['chunk_id']}]"
        formatted = ResponseFormatter().format("question", answer, context)
        self.assertIn("PDF 第 1 页", formatted)
        self.assertIn("PDF 第 2 页", formatted)
        report = CitationAnalyzer().analyze_citations(answer, context)
        self.assertEqual(
            report["cited_chunks_analysis"]["cited_chunks"][0]["page_numbers"], [1, 2]
        )
        expert = ChemicalQAExpert.__new__(ChemicalQAExpert)
        expert.retriever = Mock()
        expert.retriever.retrieve_relevant_context.return_value = context
        expert.generator = Mock(
            prompt_template=ORGANIC_ELECTROCATALYSIS_PROMPT, last_validation=None
        )
        expert.generator.generate_answer_result.return_value = GenerationResult(
            status="success", content=answer, request_sent=True, attempts=1
        )
        expert.formatter = ResponseFormatter()
        with tempfile.TemporaryDirectory() as folder:
            with patch("src.utils.artifacts.settings.OUTPUT_DIR", folder):
                expert.answer_query("question", analyze_citations=False)
            record = json.loads(
                (expert.last_run_dir / "answer.evidence.json").read_text()
            )
        self.assertEqual(record["evidence_map"][0]["source_spans"], doc["source_spans"])


if __name__ == "__main__":
    unittest.main()
