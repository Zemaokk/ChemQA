"""Synthetic R01 contract checks, not a re-evaluation of consumed reserve papers."""

import json
import tempfile
import unittest
from unittest.mock import Mock, patch

from config.answer_policy import ANSWER_POLICY_VERSION, CONSERVATIVE_PROMPT
from src.api_integration.guarded_generator import GuardedAnswerGenerator
from src.api_integration.prompt_builder import prepare_prompt
from src.api_integration.result import APIGenerationError, GenerationResult
from src.qa_system.answer_validation import audit_answer, quantities
from src.qa_system.context_selection import request_size, select_context, verify_budget
from src.qa_system.expert_system import ChemicalQAExpert
from src.qa_system.response_formatter import ResponseFormatter
from tests.test_q01_identity import identified
from tests.test_q065i_context import BODY, POLICY, hit


class AnswerValidationTests(unittest.TestCase):
    def test_conservative_template_counted_in_whole_request_budget_and_sent_once(self):
        selected = select_context(
            "机理依据？", [hit(0)], POLICY, BODY, template=CONSERVATIVE_PROMPT
        )
        prepared = selected.prepared
        self.assertEqual(prepared.prompt_version, ANSWER_POLICY_VERSION)
        self.assertEqual(
            prepared.budget["input_estimate"], request_size(prepared, BODY)
        )
        verify_budget(prepared, BODY)
        gen = GuardedAnswerGenerator()
        gen.api_handler = Mock()
        gen.api_handler.request_parameters.return_value = {"body": BODY}
        gen.api_handler.generate_result.return_value = GenerationResult(
            status="success", content="当前片段不足以确定机理。", request_sent=True
        )
        self.assertEqual(
            gen.generate_answer_result("机理依据？", prepared).status, "success"
        )
        gen.api_handler.generate_result.assert_called_once_with(
            prepared.text, prepared=prepared
        )

    def chunk(self, text):
        return identified("synthetic.pdf", b"R01 synthetic source", text)

    def check_answer(self, question, answer, source):
        chunk = self.chunk(source)
        return audit_answer(question, answer + f" [Ref {chunk['chunk_id']}]", [chunk])

    def codes(self, report):
        return {x["code"] for x in report["findings"]}

    def test_requested_signed_value_and_matching_unit_pass_without_scientific_claim(
        self,
    ):
        r = self.check_answer(
            "报告电位。", "电位为 -0.73 V。", "The potential was -0.73 V."
        )
        self.assertEqual(r["status"], "passed_lexical_checks")
        self.assertFalse(r["scientific_support_verified"])

    def test_sign_loss_is_blocked_even_when_citation_resolves(self):
        r = self.check_answer(
            "报告电位。", "电位为 0.73 V。", "The potential was -0.73 V."
        )
        self.assertIn("quantity_not_in_cited_excerpt", self.codes(r))

    def test_unsolicited_concentration_is_blocked_despite_existing_in_source(self):
        r = self.check_answer(
            "较优电位是什么？",
            "电位 3.7 V；浓度 0.83 mM。",
            "Potential 3.7 V. A separate trial gave 0.83 mM.",
        )
        self.assertIn("unrequested_quantity", self.codes(r))

    def test_unsolicited_temperature_on_rate_question_is_blocked(self):
        r = self.check_answer(
            "报告productivity和FE。",
            "productivity 37 μmol cm−2 h−1，FE 61%，温度42°C。",
            "Productivity 37 μmol cm−2 h−1 and FE 61%. Another test at 42°C.",
        )
        self.assertIn("unrequested_quantity", self.codes(r))

    def test_citation_must_be_local_to_numeric_paragraph(self):
        chunk = self.chunk("The potential was 3.7 V.")
        r = audit_answer(
            "电位是多少？", f"电位3.7 V。\n\n引用：[Ref {chunk['chunk_id']}]", [chunk]
        )
        self.assertIn("quantity_not_in_cited_excerpt", self.codes(r))

    def test_current_and_current_density_are_not_interchangeable(self):
        r = self.check_answer(
            "电流密度是多少？", "10 mA cm−2。", "The current was 10 mA."
        )
        self.assertIn("quantity_not_in_cited_excerpt", self.codes(r))

    def test_unit_superscript_and_slash_aliases_preserve_dimensions(self):
        r = self.check_answer(
            "电流密度？", "10 mA/cm2。", "A current density of 10 mA cm⁻² was used."
        )
        self.assertEqual(r["status"], "passed_lexical_checks")
        self.assertEqual(len(list(quantities("37 μmol cm−2 h−1"))), 1)

    def test_numeric_value_from_other_uncited_chunk_cannot_license_claim(self):
        a, b = self.chunk("3.7 V."), identified("other.pdf", b"other", "8.2 V.")
        r = audit_answer("电位？", f"8.2 V [Ref {a['chunk_id']}]", [a, b])
        self.assertIn("quantity_not_in_cited_excerpt", self.codes(r))

    def test_unasked_reaction_equation_blocked_even_if_verbatim(self):
        r = self.check_answer(
            "还原物种是什么？", "X• + Y− → X− + Y", "X• + Y− → X− + Y"
        )
        self.assertIn("unverified_reaction_equation", self.codes(r))

    def test_asked_verbatim_equation_passes_but_charge_edit_is_blocked(self):
        good = self.check_answer("给出反应式。", "X• + Y− → X− + Y", "X• + Y− → X− + Y")
        bad = self.check_answer("给出反应式。", "X• + Y− → XY−", "X• + Y− → X− + Y")
        self.assertEqual(good["status"], "passed_lexical_checks")
        self.assertIn("unverified_reaction_equation", self.codes(bad))

    def test_negative_selectivity_needs_explicit_local_anomaly_notice(self):
        r = self.check_answer(
            "选择性？", "选择性-73%（原文如此）。", "Selectivity (-73%)."
        )
        self.assertIn("unflagged_negative_percentage", self.codes(r))
        good = self.check_answer(
            "选择性？",
            "选择性-73%（原文异常，需核查，不能当有效性能）。",
            "Selectivity (-73%).",
        )
        self.assertEqual(good["status"], "passed_lexical_checks")

    def test_negative_relative_change_is_not_mislabeled_negative_efficiency(self):
        r = self.check_answer("FE变化？", "FE相对变化-7%。", "Relative FE change -7%.")
        self.assertNotIn("unflagged_negative_percentage", self.codes(r))

    def test_unbounded_absence_is_blocked_and_scoped_uncertainty_allowed(self):
        bad = self.check_answer("机理依据？", "全文没有对照。", "Only an excerpt.")
        good = self.check_answer(
            "机理依据？",
            "当前片段未见足够证据，不能判断全文是否没有对照。",
            "Only an excerpt.",
        )
        self.assertIn("unbounded_evidence_absence", self.codes(bad))
        self.assertNotIn("unbounded_evidence_absence", self.codes(good))

    def test_prompt_provenance_and_no_old_prepared_input_bypass(self):
        gen = GuardedAnswerGenerator()
        p = gen._prepare("q", [self.chunk("A source.")])
        self.assertEqual(p.record()["prompt_version"], ANSWER_POLICY_VERSION)
        self.assertEqual(
            p.text,
            CONSERVATIVE_PROMPT.format(
                domain=p.domain, context=p.serialized_context, question="q"
            ),
        )
        with self.assertRaises(ValueError):
            gen._prepare("q", prepare_prompt("q", [self.chunk("A source.")]))

    def test_empty_evidence_and_api_failures_do_not_trigger_validation_or_retries(self):
        gen = GuardedAnswerGenerator()
        gen.api_handler = Mock()
        self.assertEqual(gen.generate_answer_result("q", []).status, "no_evidence")
        gen.api_handler.generate_result.assert_not_called()
        failed = GenerationResult(
            status="failed", error_code="timeout", request_sent=True, attempts=1
        )
        gen.api_handler.generate_result.return_value = failed
        self.assertIs(gen.generate_answer_result("q", [self.chunk("source")]), failed)
        self.assertIsNone(gen.last_validation)
        gen.api_handler.generate_result.assert_called_once()

    def test_blocked_completion_preserves_usage_and_publishes_failure_only(self):
        chunk = self.chunk("The potential was -0.73 V.")
        expert = ChemicalQAExpert.__new__(ChemicalQAExpert)
        expert.retriever = Mock()
        expert.retriever.retrieve_relevant_context.return_value = [chunk]
        expert.generator = GuardedAnswerGenerator()
        expert.generator.api_handler = Mock()
        raw = f"0.73 V [Ref {chunk['chunk_id']}]"
        expert.generator.api_handler.generate_result.return_value = GenerationResult(
            status="success",
            content=raw,
            request_sent=True,
            attempts=1,
            usage={"total_tokens": 91},
            response_id="synthetic-response",
        )
        expert.formatter = ResponseFormatter()
        with tempfile.TemporaryDirectory() as folder:
            with (
                patch("src.utils.artifacts.settings.OUTPUT_DIR", folder),
                self.assertRaises(APIGenerationError) as cm,
            ):
                expert.answer_query("电位？", analyze_citations=False)
            self.assertEqual(cm.exception.result.error_code, "answer_validation")
            self.assertFalse(cm.exception.result.retryable)
            self.assertFalse((expert.last_run_dir / "answer.md").exists())
            record = json.loads((expert.last_run_dir / "failure.json").read_text())
        self.assertEqual(record["generation_result"]["partial_content"], raw)
        self.assertEqual(record["generation_result"]["usage"], {"total_tokens": 91})
        self.assertEqual(
            record["generation_input"]["answer_validation"]["status"], "blocked"
        )
        expert.generator.api_handler.generate_result.assert_called_once()

    def test_default_expert_installs_guarded_generator(self):
        with patch("src.qa_system.expert_system.Retriever"):
            expert = ChemicalQAExpert()
        self.assertIsInstance(expert.generator, GuardedAnswerGenerator)


if __name__ == "__main__":
    unittest.main()
