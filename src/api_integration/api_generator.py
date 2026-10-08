from config.prompts import ORGANIC_ELECTROCATALYSIS_PROMPT
from src.api_integration.api_handler import DeepSeekAPIHandler
from src.api_integration.prompt_builder import PreparedPrompt, prepare_prompt
from src.api_integration.result import GenerationResult
from src.qa_system.evidence_policy import NO_EVIDENCE_ANSWER


class DeepSeekAnswerGenerator:
    def __init__(self):
        self.api_handler = DeepSeekAPIHandler()
        self.prompt_template = ORGANIC_ELECTROCATALYSIS_PROMPT

    def generate_answer(
        self, question: str, context: list[dict] | PreparedPrompt | None
    ) -> str:
        """Text compatibility interface; API failures never become answer strings."""
        return self.generate_answer_result(question, context).require_content()

    def generate_answer_result(
        self, question: str, context: list[dict] | PreparedPrompt | None
    ) -> GenerationResult:
        prepared = self._prepare(question, context)
        if not prepared.chunks:
            return GenerationResult(status="no_evidence", content=NO_EVIDENCE_ANSWER)
        if prepared.budget is not None:
            from src.qa_system.context_selection import verify_budget

            verify_budget(prepared, self.api_handler.request_parameters()["body"])
            return self.api_handler.generate_result(prepared.text, prepared=prepared)
        return self.api_handler.generate_result(prepared.text)

    def _build_prompt(
        self, question: str, context: list[dict] | PreparedPrompt | None
    ) -> str:
        """整合提示模板"""
        return self._prepare(question, context).text

    def _prepare(
        self, question: str, context: list[dict] | PreparedPrompt | None
    ) -> PreparedPrompt:
        if isinstance(context, PreparedPrompt):
            if context.question != question:
                raise ValueError("Prepared prompt belongs to a different question")
            return context
        return prepare_prompt(question, context, template=self.prompt_template)
