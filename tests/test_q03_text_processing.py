"""Scientific characters, token budgets, source coverage and encoder guards."""

import tempfile
import unittest
from itertools import pairwise
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from src.knowledge_base.location import clean_with_offsets
from src.knowledge_base.text_processor import TextProcessor
from src.knowledge_base.token_budget import TokenBudget
from src.knowledge_base.vector_store import VectorStore
from tests.test_q02_location import page_document


class CharacterTokenizer:
    """A deterministic tokenizer to exercise sub-word and long-word boundaries."""

    is_fast = True

    def num_special_tokens_to_add(self, pair=False):
        return 2

    def __call__(self, text, **kwargs):
        positions = [(i, i + 1) for i, char in enumerate(text) if not char.isspace()]
        return {"input_ids": [1] * len(positions), "offset_mapping": positions}


def model(limit=20):
    return SimpleNamespace(
        tokenizer=CharacterTokenizer(), max_seq_length=limit, encode=Mock()
    )


class TextProcessingTests(unittest.TestCase):
    def processor(self, limit=20, overlap=3):
        processor = TextProcessor(model=model(limit))
        processor.token_overlap = overlap
        return processor

    def test_only_whitespace_changes_chemical_expressions(self):
        raw = "\t[Ni(CN)₄]²⁻ + HSO₄− → H₂O; 25 °C, 90%, 1.5 V vs. RHE; ΔG ≤ 0\n"
        expected = raw.strip()
        self.assertEqual(TextProcessor().clean_text(raw), expected)
        self.assertNotEqual(TextProcessor(legacy=True).clean_text(raw), expected)
        cleaned, positions = clean_with_offsets(raw, preserve_symbols=True)
        self.assertEqual(cleaned, expected)
        for char, (start, end) in zip(cleaned, positions, strict=True):
            self.assertEqual(char, " " if raw[start:end].isspace() else raw[start:end])

    def test_multilingual_long_word_chunks_cover_every_nonwhitespace_character(self):
        processor = self.processor()
        text = processor.clean_text(
            "甲乙丙丁戊己庚辛壬癸" * 8 + "\n" + "a" * 70 + " HSO₄− + 25 °C"
        )
        intervals = processor.split_intervals(text)
        covered = set()
        for start, end in intervals:
            self.assertGreater(end, start)
            self.assertLessEqual(processor.budget.count(text[start:end]), 20)
            covered.update(range(start, end))
        self.assertTrue(
            all(i in covered for i, char in enumerate(text) if not char.isspace())
        )
        self.assertEqual(intervals[-1][1], len(text))
        self.assertTrue(any(a[1] > b[0] for a, b in pairwise(intervals)))

    def test_word_count_is_distinct_from_tokens_and_includes_special_tokens(self):
        processor = self.processor()
        chunk = processor.process_document(page_document(["HSO₄− + 25 °C\n"]))[0]
        meta = chunk["metadata"]
        self.assertEqual(meta["word_count"], 4)
        self.assertEqual(meta["embedding_token_count"], 12)
        self.assertNotIn("num_tokens", meta)
        self.assertEqual(meta["embedding_token_limit"], 20)

    def test_cross_page_locations_reconstruct_new_chemical_text(self):
        processor = self.processor(limit=40, overlap=3)
        document = page_document(["HSO₄− +\n", "", "[Ni(CN)₄]²⁻ 25 °C\n"])
        chunk = processor.process_document(document)[0]
        self.assertEqual(chunk["metadata"]["page_numbers"], [1, 3])
        spans = chunk["metadata"]["source_spans"]
        self.assertEqual(
            processor.clean_text("".join(s["raw_text"] for s in spans)), chunk["text"]
        )
        self.assertIn("²⁻", chunk["text"])

    def test_empty_whitespace_only_input_and_zero_overlap(self):
        processor = self.processor(overlap=0)
        self.assertEqual(processor.process_document(page_document([" \n\t"])), [])
        intervals = processor.split_intervals("a" * 60)
        self.assertEqual(intervals, [(0, 18), (18, 36), (36, 54), (54, 60)])

    def test_invalid_overlap_and_limit_fail_explicitly(self):
        for overlap in (-1, 18, 19):
            with self.assertRaises(ValueError):
                self.processor(overlap=overlap).split_text("evidence")
        with self.assertRaises(ValueError):
            TokenBudget(model(limit=2))

    def test_validation_failure_does_not_replace_active_files(self):
        from src.pipeline.vector_index_builder import VectorIndexBuilder

        builder = VectorIndexBuilder.__new__(VectorIndexBuilder)
        builder.vector_store = SimpleNamespace(model=model())
        builder.process_documents = Mock(return_value=[{"text": "staged"}])
        builder.save_processed_chunks = Mock()

        def write_staged(chunks, output_dir):
            (Path(output_dir) / "vector_index.json").write_text("{}")

        builder.build_index = Mock(side_effect=write_staged)
        with tempfile.TemporaryDirectory() as folder:
            chunks_path = Path(folder) / "processed_chunks.json"
            index_path = Path(folder) / "vector_index.json"
            chunks_path.write_bytes(b"old processed")
            index_path.write_bytes(b"old index")
            with (
                patch(
                    "scripts.validate_q03.validate",
                    side_effect=ValueError("bad staged data"),
                ),
                patch(
                    "src.pipeline.vector_index_builder.settings.PROCESSED_DIR", folder
                ),
                patch(
                    "src.pipeline.vector_index_builder.settings.VECTOR_DB_DIR", folder
                ),
                self.assertRaisesRegex(ValueError, "bad staged data"),
            ):
                builder.run_pipeline()
            self.assertEqual(chunks_path.read_bytes(), b"old processed")
            self.assertEqual(index_path.read_bytes(), b"old index")

    def test_failed_pdf_extraction_stops_partial_rebuild(self):
        from src.pipeline.vector_index_builder import VectorIndexBuilder

        builder = VectorIndexBuilder.__new__(VectorIndexBuilder)
        builder.pdf_loader = Mock()
        builder.pdf_loader.load_pdfs.return_value = ["unreadable.pdf"]
        builder.pdf_loader.load_pdf.return_value = []
        with self.assertRaisesRegex(ValueError, "rebuild stopped"):
            builder.process_documents()

    def test_oversized_query_and_document_never_reach_encoder(self):
        store = VectorStore.__new__(VectorStore)
        store.model = model()
        store.budget = TokenBudget(store.model)
        for texts in ("a" * 19, ["okay", "a" * 19]):
            with self.assertRaisesRegex(ValueError, "model limit"):
                store.encode_texts(texts)
        store.model.encode.assert_not_called()
        store.encode_texts("a" * 18)
        store.model.encode.assert_called_once_with("a" * 18)


if __name__ == "__main__":
    unittest.main()
