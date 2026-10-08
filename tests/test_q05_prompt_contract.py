"""Generation receives explicit evidence, and new citations resolve only to that input."""

import json
import tempfile
import unittest
from unittest.mock import Mock, patch

from config.prompts import PROMPT_VERSION
from src.api_integration.api_generator import DeepSeekAnswerGenerator
from src.api_integration.prompt_builder import prepare_prompt
from src.api_integration.result import GenerationResult
from src.knowledge_base.identity import normalize_chunk
from src.knowledge_base.retriever import Retriever
from src.knowledge_base.text_processor import TextProcessor
from src.qa_system.citation_analyzer import CitationAnalyzer
from src.qa_system.context import CONTEXT_VERSION, serialize_context
from src.qa_system.evidence import resolve_citations
from src.qa_system.expert_system import ChemicalQAExpert
from src.qa_system.response_formatter import ResponseFormatter
from tests.test_q01_identity import identified
from tests.test_q02_location import page_document


class PromptContractTests(unittest.TestCase):
    def setUp(self):
        self.a = identified(
            "A.pdf", b"PDF A", 'HSO₄− + H₂O; 25 °C, 90%\n"quotes" {context} [Ref fake]'
        )
        self.b = identified("B.pdf", b"PDF B", "Another independent result", 0)
        self.generator = DeepSeekAnswerGenerator()
        self.generator.api_handler = Mock()
        self.generator.api_handler.generate_result.return_value = GenerationResult(
            status="success", content="mock answer", request_sent=True, attempts=1
        )

    def test_json_roundtrip_preserves_complete_scientific_text_and_ids(self):
        text = serialize_context([self.a, self.b])
        data = json.loads(text)
        self.assertEqual(data["context_version"], CONTEXT_VERSION)
        self.assertEqual(data["evidence_count"], 2)
        for item, original in zip(data["evidence"], [self.a, self.b], strict=True):
            self.assertEqual(item["text"], original["text"])
            self.assertEqual(item["citation"], f"[Ref {original['chunk_id']}]")
            self.assertEqual(item["doc_id"], original["doc_id"])
        self.assertEqual(data["evidence"][0]["source_title"], "A.pdf")
        self.assertNotIn("chunk_index", data["evidence"][0])
        self.assertNotIn("metadata", data["evidence"][0])

    def test_prompt_embeds_json_instead_of_python_repr_and_uses_domain(self):
        with patch("src.api_integration.prompt_builder.settings.DOMAIN", "test-domain"):
            prepared = prepare_prompt("Question with {braces}", [self.a, self.b])
        self.assertIn(prepared.serialized_context, prepared.text)
        self.assertIn("test-domain", prepared.text)
        self.assertIn("Question with {braces}", prepared.text)
        self.assertNotIn(str([self.a, self.b]), prepared.text)
        self.assertIn("只引用 evidence 数组中实际存在", prepared.text)
        self.assertEqual(prepared.record()["prompt_version"], PROMPT_VERSION)

    def test_nested_records_and_duplicate_aliases_share_one_input_snapshot(self):
        nested = {
            "text": self.a["text"],
            "metadata": {k: v for k, v in self.a.items() if k != "text"},
        }
        alias = {**self.a, "source": "A copy.pdf"}
        prepared = prepare_prompt("q", [nested, alias, self.b])
        self.assertEqual(len(prepared.chunks), 2)
        self.assertEqual(prepared.chunks[0]["sources"], ["A copy.pdf", "A.pdf"])
        nested["text"] = "changed caller data"
        copy = prepared.chunks
        copy[0]["text"] = "changed returned data"
        self.assertEqual(prepared.chunks[0]["text"], self.a["text"])
        self.assertEqual(
            json.loads(prepared.serialized_context)["evidence"][0]["text"],
            self.a["text"],
        )

    def test_pages_are_explicit_and_missing_locations_are_not_guessed(self):
        located = normalize_chunk(
            TextProcessor(legacy=True).process_document(
                page_document(["one two\n", "three four\n"])
            )[0]
        )
        data = json.loads(serialize_context([located, self.a]))["evidence"]
        self.assertEqual(data[0]["page_numbers"], [1, 2])
        self.assertEqual(data[0]["location_status"], "located")
        self.assertEqual(data[1]["page_numbers"], [])
        self.assertEqual(data[1]["location_status"], "unavailable")
        self.assertEqual(data[1]["location_reason"], "page_text_not_supplied")

    def test_none_and_empty_inputs_have_the_same_explicit_empty_evidence(self):
        self.assertEqual(serialize_context(None), serialize_context([]))
        prepared = prepare_prompt("q", None)
        self.assertEqual(json.loads(prepared.serialized_context)["evidence_count"], 0)
        self.assertEqual(prepared.chunks, [])
        self.assertNotIn("\nNone\n", prepared.text)
        self.assertIn("evidence_count 为 0", prepared.text)

    def test_raw_strings_bad_records_and_empty_questions_fail_before_api(self):
        for context in (
            "raw context",
            {"text": "invalid"},
            ["not a dict"],
            [{**self.a, "text": "tampered"}],
        ):
            with self.assertRaises((TypeError, ValueError)):
                self.generator.generate_answer("q", context)
        for question in ("", " \n", None):
            with self.assertRaises(ValueError):
                self.generator.generate_answer(question, [self.a])
        self.generator.api_handler.generate_result.assert_not_called()

    def test_prepared_prompt_is_sent_exactly_once_and_rejects_question_mismatch(self):
        prepared = prepare_prompt("q", [self.a])
        self.assertEqual(self.generator.generate_answer("q", prepared), "mock answer")
        self.generator.api_handler.generate_result.assert_called_once_with(
            prepared.text
        )
        with self.assertRaises(ValueError):
            self.generator.generate_answer("other question", prepared)
        self.assertEqual(self.generator.api_handler.generate_result.call_count, 1)

    def test_new_citations_reject_unique_legacy_labels_and_bare_numbers(self):
        answer = f"Good [Ref {self.a['chunk_id']}] local [Ref 0] source [Ref A.pdf] number [1] unknown [Ref invented]"
        resolved = resolve_citations(answer, [self.a], allow_legacy=False)
        self.assertEqual(resolved["counts"], {self.a["chunk_id"]: 1})
        self.assertEqual(
            [u["reason"] for u in resolved["unresolved"]],
            ["noncanonical"] * 3 + ["unknown"],
        )
        formatted = ResponseFormatter().format_answer(
            answer, [self.a], allow_legacy=False
        )
        self.assertEqual(formatted["formatted_answer"].count("未解析引用"), 4)
        analysis = CitationAnalyzer().analyze_citations(
            answer, [self.a], allow_legacy=False
        )
        self.assertEqual(
            analysis["unresolved_citations"], formatted["unresolved_citations"]
        )
        self.assertEqual(analysis["citation_coverage"]["cited_count"], 1)
        legacy = resolve_citations("[Ref 0] [Ref A.pdf] [1]", [self.a])
        self.assertEqual(legacy["counts"], {self.a["chunk_id"]: 2})
        self.assertEqual(legacy["unresolved"], [])

    def test_retriever_string_mode_uses_same_json_contract_including_no_results(self):
        retriever = Retriever.__new__(Retriever)
        retriever.vector_store = Mock()
        retriever.vector_store.similarity_search.return_value = [
            {"document": self.a, "score": 0.8}
        ]
        self.assertEqual(
            retriever.retrieve_relevant_context("q"), serialize_context([self.a])
        )
        retriever.vector_store.similarity_search.return_value = []
        self.assertEqual(
            retriever.retrieve_relevant_context("q"), serialize_context([])
        )
        self.assertEqual(
            retriever.retrieve_relevant_context("q", return_dict_list=True), []
        )

    def test_expert_sidecar_matches_exact_api_prompt_and_evidence_snapshot(self):
        expert = ChemicalQAExpert.__new__(ChemicalQAExpert)
        expert.retriever = Mock()
        expert.retriever.retrieve_relevant_context.return_value = [
            self.a,
            self.b,
            self.a,
        ]
        expert.generator = self.generator
        expert.formatter = ResponseFormatter()
        expert.generator.api_handler.generate_result.return_value = GenerationResult(
            status="success",
            content=f"Result [Ref {self.b['chunk_id']}] bad [Ref 0] [1]",
            request_sent=True,
            attempts=1,
        )
        with tempfile.TemporaryDirectory() as folder:
            with patch("src.utils.artifacts.settings.OUTPUT_DIR", folder):
                answer = expert.answer_query("q", analyze_citations=False)
            saved = json.loads(
                (expert.last_run_dir / "answer.evidence.json").read_text()
            )
        sent = expert.generator.api_handler.generate_result.call_args.args[0]
        self.assertEqual(sent, saved["generation_input"]["prompt"])
        self.assertEqual(
            saved["generation_input"]["allowed_chunk_ids"],
            [self.a["chunk_id"], self.b["chunk_id"]],
        )
        self.assertEqual(
            [d["chunk_id"] for d in saved["evidence_map"]],
            saved["generation_input"]["allowed_chunk_ids"],
        )
        self.assertEqual(len(saved["unresolved_citations"]), 2)
        self.assertIn("Result [2]", answer)
        self.assertEqual(answer.count("未解析引用："), 2)


if __name__ == "__main__":
    unittest.main()
