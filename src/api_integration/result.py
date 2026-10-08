"""Explicit generation outcomes; operational success does not verify scientific support."""

from dataclasses import asdict, dataclass, field
from typing import Literal


@dataclass(frozen=True)
class GenerationResult:
    status: Literal["success", "no_evidence", "failed", "truncated"]
    content: str | None = None
    error_code: str | None = None
    error_message: str | None = None
    retryable: bool = False
    request_sent: bool = False
    attempts: int = 0
    http_status: int | None = None
    finish_reason: str | None = None
    requested_model: str | None = None
    returned_model: str | None = None
    response_id: str | None = None
    usage: dict = field(default_factory=dict)
    request_parameters: dict = field(default_factory=dict)
    reasoning_content_present: bool = False
    reasoning_characters: int = 0
    elapsed_seconds: float = 0.0
    attempt_history: tuple[dict, ...] = ()
    partial_content: str | None = None

    def __post_init__(self):
        if self.status not in ("success", "no_evidence", "failed", "truncated"):
            raise ValueError("Unknown generation status")
        if self.completed:
            if not isinstance(self.content, str) or not self.content.strip():
                raise ValueError("Completed generation requires nonempty text")
        elif self.content is not None or not self.error_code:
            raise ValueError("Failed generation requires an error code and no answer")

    @property
    def completed(self) -> bool:
        return self.status in ("success", "no_evidence")

    def record(self) -> dict:
        record = asdict(self)
        record.pop("content")
        return {"schema": "chemqa-generation-result-v1", **record}

    def require_content(self) -> str:
        if not self.completed:
            exception = (
                APIConfigurationError
                if self.error_code == "configuration"
                else APIGenerationError
            )
            raise exception(self)
        return self.content


class APIGenerationError(RuntimeError):
    def __init__(self, result: GenerationResult):
        self.result = result
        super().__init__(result.error_message or result.error_code)


class APIConfigurationError(APIGenerationError, ValueError):
    """Keep missing-key ValueError compatibility without losing structured details."""


def execution_status(record: dict) -> str:
    """Legacy records without explicit status remain unverified, never inferred successful."""
    status = record.get("status")
    if status in ("success", "no_evidence", "failed", "truncated", "pending"):
        return status
    return "unverified"
