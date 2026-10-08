"""Whole evidence, budget boundaries, request drift and frozen citation contracts."""

import copy
import json
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import Mock, patch

from config.settings import settings
from src.api_integration.api_generator import DeepSeekAnswerGenerator
from src.api_integration.api_handler import DeepSeekAPIHandler
from src.api_integration.prompt_builder import prepare_prompt
from src.api_integration.result import GenerationResult
from src.qa_system.context_selection import (
    payload_for,
    request_size,
    select_context,
    span_overlap,
    validate_policy,
    verify_budget,
)
from src.qa_system.expert_system import ChemicalQAExpert
from src.qa_system.response_formatter import ResponseFormatter
from tests.test_q01_identity import identified

POLICY = json.loads(Path("config/q065i_context.json").read_text())
BODY = {
    "model": "test-provider",
    "max_tokens": 4096,
    "thinking": {"type": "disabled"},
    "stream": False,
    "temperature": 0.3,
}


def hit(i, text=None, doc=None):
    d = identified(
        "paper.pdf",
        str(doc if doc is not None else i).encode(),
        text or "evidence " + str(i),
        i,
    )
    return {"document": d, "score": 100 - i, "score_kind": "reranker_logit_difference"}


def located(i, start, end, doc="a", page=1):
    h = hit(i, "x" * (end - start), doc)
    h["document"].update(
        location_version="page-text-v1",
        location_status="located",
        page_numbers=[page],
        source_spans=[
            {
                "page_number": page,
                "char_start": start,
                "char_end": end,
                "raw_text": "x" * (end - start),
            }
        ],
    )
    return h


class SelectionTests(unittest.TestCase):
    def test_input_estimate_counts_whole_payload_and_unicode_escaping(self):
        p = prepare_prompt("电位？", [hit(0)["document"]])
        self.assertEqual(
            request_size(p, BODY),
            len(json.dumps(payload_for(p, BODY), allow_nan=False).encode()),
        )
        self.assertGreater(request_size(p, BODY), len(p.text.encode()))
        self.assertIn("messages", payload_for(p, BODY))

    def test_identity_text_dedup_and_full_chunks_unchanged(self):
        a = hit(0)
        inputs = [a, copy.deepcopy(a), hit(1, a["document"]["text"]), hit(2)]
        original = copy.deepcopy(inputs)
        result = select_context("q", inputs, POLICY, BODY)
        self.assertEqual(len(result.prepared.chunks), 2)
        self.assertEqual(
            [r["reason"] for r in result.audit["records"]],
            [None, "duplicate_chunk_id", "duplicate_text", None],
        )
        self.assertEqual(inputs, original)
        self.assertEqual(result.prepared.chunks[0]["text"], a["document"]["text"])

    def test_per_document_cap_allows_later_other_documents_without_forcing_minimum(
        self,
    ):
        hits = [hit(i, doc="one") for i in range(8)] + [hit(8, doc="two")]
        result = select_context("q", hits, POLICY, BODY)
        self.assertEqual(
            [r["rank"] for r in result.audit["records"] if r["selected"]],
            [1, 2, 3, 4, 5, 6, 9],
        )
        self.assertEqual(result.audit["selected_document_count"], 2)
        one = select_context("q", hits[:2], POLICY, BODY)
        self.assertEqual(one.audit["selected_document_count"], 1)

    def test_interval_union_avoids_double_count_and_cross_document_page_overlap(self):
        c = {
            "doc_id": "a",
            "location_status": "located",
            "source_spans": [{"page_number": 1, "char_start": 0, "char_end": 100}],
        }
        old = [
            {
                **c,
                "source_spans": [{"page_number": 1, "char_start": 0, "char_end": 40}],
            },
            {
                **c,
                "source_spans": [{"page_number": 1, "char_start": 20, "char_end": 60}],
            },
        ]
        self.assertEqual(span_overlap(c, old), 0.6)
        self.assertEqual(span_overlap({**c, "doc_id": "b"}, old), 0)
        self.assertEqual(
            span_overlap(
                {
                    **c,
                    "source_spans": [
                        {"page_number": 2, "char_start": 0, "char_end": 100}
                    ],
                },
                old,
            ),
            0,
        )

    def test_source_overlap_filter_keeps_original_text_and_location(self):
        # Fixture version copied from the actual location contract.
        from src.knowledge_base.location import LOCATION_VERSION

        a, b = located(0, 0, 100), located(1, 30, 120)
        for h in [a, b]:
            h["document"]["location_version"] = LOCATION_VERSION
        result = select_context("q", [a, b], POLICY, BODY)
        self.assertEqual(result.audit["records"][1]["reason"], "source_span_overlap")
        self.assertEqual(
            result.prepared.chunks[0]["source_spans"], a["document"]["source_spans"]
        )

    def test_duplicate_identity_with_conflicting_locations_is_not_silently_skipped(
        self,
    ):
        from src.knowledge_base.location import LOCATION_VERSION

        a = located(0, 0, 100)
        a["document"]["location_version"] = LOCATION_VERSION
        b = copy.deepcopy(a)
        b["document"]["source_spans"][0].update(char_start=1, char_end=101)
        with self.assertRaisesRegex(ValueError, "Conflicting verified locations"):
            select_context("q", [a, b], POLICY, BODY)

    def test_budget_skips_overlong_whole_chunk_and_continues_to_shorter_candidate(self):
        small = hit(1, "short evidence")
        size = request_size(prepare_prompt("q", [small["document"]]), BODY)
        policy = {**POLICY, "input_estimate_limit": size}
        result = select_context("q", [hit(0, "x" * 40000), small], policy, BODY)
        self.assertEqual(result.audit["records"][0]["reason"], "input_budget")
        self.assertEqual(result.prepared.chunks, [small["document"]])
        self.assertEqual(result.prepared.budget["input_estimate"], size)

    def test_template_question_overflow_and_output_budget_mismatch_raise(self):
        with self.assertRaisesRegex(ValueError, "alone exceeds"):
            select_context("x" * 40000, [], POLICY, BODY)
        with self.assertRaisesRegex(ValueError, "output budget"):
            select_context("q", [], POLICY, {**BODY, "max_tokens": 8192})

    def test_policy_and_candidate_count_are_validated(self):
        for change in [
            {"max_chunks": True},
            {"max_chunks": 51},
            {"max_chunks_per_document": 11},
            {"protocol_token_reserve": 10000},
            {"neighbor_expansion": True},
            {"maximum_existing_span_overlap": float("nan")},
        ]:
            with self.assertRaises(ValueError):
                validate_policy({**POLICY, **change})
        with self.assertRaisesRegex(ValueError, "50"):
            select_context("q", [hit(i) for i in range(51)], POLICY, BODY)

    def test_snapshot_is_immutable_and_parameter_prompt_policy_drift_fail(self):
        result = select_context("q", [hit(0)], POLICY, BODY)
        p = result.prepared
        p.chunks[0]["text"] = "mutated"
        p.budget["request_body"]["model"] = "mutated"
        self.assertEqual(verify_budget(p, BODY)["request_body"], BODY)
        for changed in [{**BODY, "model": "other"}, {**BODY, "max_tokens": 10}]:
            with self.assertRaises(ValueError):
                verify_budget(p, changed)
        with self.assertRaises(ValueError):
            verify_budget(replace(p, text=p.text + "extra"), BODY)
        budget = p.budget
        budget["policy"]["input_estimate_limit"] += 1
        with self.assertRaises(ValueError):
            verify_budget(replace(p, budget_json=json.dumps(budget)), BODY)


class GenerationIntegrationTests(unittest.TestCase):
    def test_candidate_constructor_requires_both_profiles_and_records_source_hashes(
        self,
    ):
        for kwargs in [{"reranker_profile": "h"}, {"context_policy": "i"}]:
            with self.assertRaisesRegex(ValueError, "both"):
                ChemicalQAExpert(**kwargs)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            profile = root / "reranker_profile.json"
            profile.write_text("{}")
            (root / "run.json").write_text("{}")
            policy = root / "policy.json"
            policy.write_text(json.dumps(POLICY))
            with (
                patch("src.qa_system.expert_system.Retriever") as retriever,
                patch("src.qa_system.expert_system.DeepSeekAnswerGenerator"),
            ):
                expert = ChemicalQAExpert(
                    reranker_profile=profile, context_policy=policy
                )
            retriever.assert_called_once_with(reranker_profile=profile)
            self.assertEqual(expert.context_policy, POLICY)
            self.assertEqual(
                len(expert.candidate_provenance["reranker_run_sha256"]), 64
            )

    def generator(self):
        gen = DeepSeekAnswerGenerator()
        gen.api_handler = Mock()
        gen.api_handler.request_parameters.return_value = {"body": BODY}
        gen.api_handler.generate_result.return_value = GenerationResult(
            status="success", content="ok"
        )
        return gen

    def test_empty_selection_stops_without_api_and_records_reason(self):
        result = select_context("q", [hit(0, "x" * 40000)], POLICY, BODY)
        gen = self.generator()
        self.assertEqual(
            gen.generate_answer_result("q", result.prepared).status, "no_evidence"
        )
        gen.api_handler.generate_result.assert_not_called()
        self.assertEqual(
            result.audit["empty_selection_reason"], "no_whole_chunk_fits_policy"
        )

    def test_generator_uses_exact_prepared_snapshot_and_rejects_config_drift(self):
        p = select_context("q", [hit(0)], POLICY, BODY).prepared
        gen = self.generator()
        gen.generate_answer_result("q", p)
        gen.api_handler.generate_result.assert_called_once_with(p.text, prepared=p)
        gen.api_handler.generate_result.reset_mock()
        gen.api_handler.request_parameters.return_value = {
            "body": {**BODY, "model": "changed"}
        }
        with self.assertRaises(ValueError):
            gen.generate_answer_result("q", p)
        gen.api_handler.generate_result.assert_not_called()

    def test_actual_send_boundary_blocks_message_mutation_before_network(self):
        handler = DeepSeekAPIHandler()
        handler.config["api_key"] = "test-fixture-only"
        handler.request_parameters = Mock(return_value={"body": BODY})
        p = select_context("q", [hit(0)], POLICY, BODY).prepared
        with patch("src.api_integration.api_handler.requests.post") as post:
            with self.assertRaisesRegex(ValueError, "Messages differ"):
                handler.send_request(
                    [{"role": "user", "content": p.text + "changed"}], prepared=p
                )
            post.assert_not_called()

    def test_mock_transport_receives_same_budgeted_request(self):
        handler = DeepSeekAPIHandler()
        handler.config["api_key"] = "test-fixture-only"
        body = handler.request_parameters()["body"]
        p = select_context("q", [hit(0)], POLICY, body).prepared
        response = Mock(status_code=200)
        response.json.return_value = {
            "choices": [
                {
                    "message": {"role": "assistant", "content": "ok"},
                    "finish_reason": "stop",
                }
            ]
        }
        with patch(
            "src.api_integration.api_handler.requests.post", return_value=response
        ) as post:
            self.assertEqual(
                handler.generate_result(p.text, prepared=p).status, "success"
            )
            self.assertEqual(post.call_args.kwargs["json"], payload_for(p, body))

    def test_expert_saves_selection_frozen_request_and_canonical_mapping(self):
        expert = ChemicalQAExpert.__new__(ChemicalQAExpert)
        expert.context_policy = POLICY
        expert.retriever = Mock()
        doc = hit(0)["document"]
        expert.retriever.search.return_value = [{"document": doc, "score": 8}]
        expert.generator = self.generator()
        expert.generator.api_handler.generate_result.return_value = GenerationResult(
            status="success", content="Supported [Ref " + doc["chunk_id"] + "]"
        )
        expert.formatter = ResponseFormatter()
        with (
            tempfile.TemporaryDirectory() as tmp,
            patch.object(settings, "OUTPUT_DIR", tmp),
        ):
            expert.answer_query("q", analyze_citations=False)
            record = json.loads(
                (expert.last_run_dir / "answer.evidence.json").read_text()
            )
        self.assertEqual(
            record["generation_input"]["context_selection"]["selected_count"], 1
        )
        self.assertIsNotNone(record["generation_input"]["request_budget"])
        self.assertEqual(
            record["generation_input"]["allowed_chunk_ids"], [doc["chunk_id"]]
        )
        self.assertEqual(record["evidence_map"][0]["chunk_id"], doc["chunk_id"])
        expert.retriever.retrieve_relevant_context.assert_not_called()


if __name__ == "__main__":
    unittest.main()
