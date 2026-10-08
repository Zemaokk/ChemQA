"""Prepare one immutable input snapshot for generation and later citation auditing."""

import hashlib
import json
from dataclasses import dataclass

from config.answer_policy import ANSWER_POLICY_VERSION, CONSERVATIVE_PROMPT
from config.prompts import ORGANIC_ELECTROCATALYSIS_PROMPT, PROMPT_VERSION
from config.settings import settings
from src.qa_system.context import CONTEXT_VERSION, normalize_context, serialize_context


@dataclass(frozen=True)
class PreparedPrompt:
    question: str
    text: str
    serialized_context: str
    evidence_json: str
    template_sha256: str
    domain: str
    budget_json: str | None = None
    prompt_version: str = PROMPT_VERSION

    @property
    def budget(self) -> dict | None:
        return json.loads(self.budget_json) if self.budget_json is not None else None

    @property
    def chunks(self) -> list[dict]:
        # Each consumer receives a fresh copy of the same frozen evidence snapshot.
        return json.loads(self.evidence_json)

    def record(self) -> dict:
        return {
            "prompt_version": self.prompt_version,
            "context_version": CONTEXT_VERSION,
            "template_sha256": self.template_sha256,
            "domain": self.domain,
            "prompt": self.text,
            "serialized_context": self.serialized_context,
            "allowed_chunk_ids": [chunk["chunk_id"] for chunk in self.chunks],
            "citation_policy": "canonical_chunk_id_only",
            **({"request_budget": self.budget} if self.budget is not None else {}),
        }


def prepare_prompt(
    question: str,
    context: list[dict] | None,
    *,
    template: str = ORGANIC_ELECTROCATALYSIS_PROMPT,
) -> PreparedPrompt:
    if not isinstance(question, str) or not question.strip():
        raise ValueError("A nonempty question is required")
    chunks = normalize_context(context)
    frozen = json.dumps(chunks, ensure_ascii=False)
    serialized = serialize_context(json.loads(frozen))
    domain = settings.DOMAIN
    text = template.format(domain=domain, context=serialized, question=question)
    return PreparedPrompt(
        question=question,
        text=text,
        serialized_context=serialized,
        evidence_json=frozen,
        template_sha256=hashlib.sha256(template.encode()).hexdigest(),
        domain=domain,
        prompt_version=ANSWER_POLICY_VERSION
        if template == CONSERVATIVE_PROMPT
        else PROMPT_VERSION,
    )
