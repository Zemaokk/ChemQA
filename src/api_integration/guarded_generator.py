"""R01 generation policy; rejected completions retain diagnostics, never retry."""

import hashlib
from dataclasses import replace

from config.answer_policy import ANSWER_POLICY_VERSION, CONSERVATIVE_PROMPT
from src.api_integration.api_generator import DeepSeekAnswerGenerator
from src.qa_system.answer_validation import audit_answer


class GuardedAnswerGenerator(DeepSeekAnswerGenerator):
    def __init__(self):
        super().__init__()
        self.prompt_template = CONSERVATIVE_PROMPT
        self.last_validation = None

    def _prepare(self, question, context):
        prepared = super()._prepare(question, context)
        if (
            prepared.prompt_version != ANSWER_POLICY_VERSION
            or prepared.template_sha256
            != hashlib.sha256(CONSERVATIVE_PROMPT.encode()).hexdigest()
        ):
            raise ValueError(
                "Guarded generation requires the conservative prepared prompt"
            )
        return prepared

    def generate_answer_result(self, question, context):
        self.last_validation = None
        prepared = self._prepare(question, context)
        result = super().generate_answer_result(question, prepared)
        if result.status != "success":
            return result
        self.last_validation = audit_answer(question, result.content, prepared.chunks)
        if self.last_validation["status"] == "blocked":
            return replace(
                result,
                status="failed",
                content=None,
                partial_content=result.content,
                error_code="answer_validation",
                error_message="回答包含未通过保真检查的扩展数值、反应式或证据断言；请核查已保存诊断。",
                retryable=False,
            )
        return result
