import math
import time
from dataclasses import replace

import requests

from config.settings import settings
from src.api_integration.result import APIConfigurationError, GenerationResult
from src.utils.logger import logger


class DeepSeekAPIHandler:
    def __init__(self):
        self.config = dict(settings.DEEPSEEK_API_CONFIG)
        self.headers = {"Content-Type": "application/json"}

    def send_request(self, messages: list, *, prepared=None) -> GenerationResult:
        """One attempt. Never log raw provider bodies, headers or network exception text."""
        if not self.config["api_key"]:
            raise APIConfigurationError(
                GenerationResult(
                    status="failed",
                    error_code="configuration",
                    error_message="DEEPSEEK_API_KEY is not configured. Set it in the environment or project .env.",
                    requested_model=self.config["model"],
                )
            )
        parameters = self.request_parameters()
        payload = {**parameters["body"], "messages": messages}
        if prepared is not None:
            from src.qa_system.context_selection import payload_for, verify_budget

            verify_budget(prepared, parameters["body"])
            if payload != payload_for(prepared, parameters["body"]):
                raise ValueError("Messages differ from frozen budgeted request")
        metadata = {
            "request_sent": True,
            "attempts": 1,
            "requested_model": self.config["model"],
            "request_parameters": parameters,
        }
        try:
            response = requests.post(
                f"{self.config['base_url']}/chat/completions",
                headers={
                    **self.headers,
                    "Authorization": f"Bearer {self.config['api_key']}",
                },
                json=payload,
                timeout=(self.config["connect_timeout"], self.config["read_timeout"]),
                allow_redirects=False,
            )
        except requests.exceptions.Timeout:
            return GenerationResult(
                status="failed",
                error_code="timeout",
                error_message="API request timed out.",
                retryable=True,
                **metadata,
            )
        except requests.exceptions.RequestException:
            return GenerationResult(
                status="failed",
                error_code="network",
                error_message="API network request failed.",
                retryable=True,
                **metadata,
            )
        metadata["http_status"] = response.status_code
        if response.status_code != 200:
            return GenerationResult(
                status="failed",
                error_code="rate_limit" if response.status_code == 429 else "http",
                error_message=f"API returned HTTP {response.status_code}.",
                retryable=response.status_code in (429, 500, 502, 503, 504),
                **metadata,
            )
        try:
            data = response.json()
        except ValueError:
            return self._invalid(metadata)
        if not isinstance(data, dict) or data.get("error") is not None:
            return self._invalid(metadata)
        for source, target in (("model", "returned_model"), ("id", "response_id")):
            if isinstance(data.get(source), str):
                metadata[target] = data[source]
        usage = data.get("usage")
        if isinstance(usage, dict):
            metadata["usage"] = {
                key: value
                for key, value in usage.items()
                if key
                in (
                    "prompt_tokens",
                    "completion_tokens",
                    "total_tokens",
                    "prompt_cache_hit_tokens",
                    "prompt_cache_miss_tokens",
                )
                and isinstance(value, int)
                and not isinstance(value, bool)
                and value >= 0
            }
            for detail_name, allowed in (
                ("completion_tokens_details", ("reasoning_tokens",)),
                ("prompt_tokens_details", ("cached_tokens",)),
            ):
                detail = usage.get(detail_name)
                if isinstance(detail, dict):
                    clean = {
                        key: value
                        for key, value in detail.items()
                        if key in allowed and type(value) is int and value >= 0
                    }
                    if clean:
                        metadata["usage"][detail_name] = clean
        choices = data.get("choices")
        if (
            not isinstance(choices, list)
            or len(choices) != 1
            or not isinstance(choices[0], dict)
        ):
            return self._invalid(metadata)
        choice = choices[0]
        message, reason = choice.get("message"), choice.get("finish_reason")
        if not isinstance(message, dict) or not isinstance(reason, str):
            return self._invalid(metadata)
        metadata["finish_reason"] = reason
        reasoning = message.get("reasoning_content")
        if reasoning is not None and not isinstance(reasoning, str):
            return self._invalid(metadata)
        metadata["reasoning_content_present"] = bool(reasoning)
        metadata["reasoning_characters"] = len(reasoning or "")
        content = message.get("content")
        if content is not None and not isinstance(content, str):
            return self._invalid(metadata)
        if reason != "stop":
            known = reason in (
                "length",
                "content_filter",
                "tool_calls",
                "insufficient_system_resource",
                "aborted",
            )
            if not known:
                return self._invalid(metadata)
            return GenerationResult(
                status="truncated" if reason == "length" else "failed",
                error_code="length" if reason == "length" else "incomplete",
                error_message=f"API generation did not complete normally ({reason}).",
                retryable=reason == "insufficient_system_resource",
                partial_content=content,
                **metadata,
            )
        if (
            message.get("refusal")
            or message.get("tool_calls")
            or message.get("role", "assistant") != "assistant"
        ):
            return self._invalid(metadata)
        if not isinstance(content, str) or not content.strip():
            return self._invalid(metadata)
        return GenerationResult(status="success", content=content, **metadata)

    def request_parameters(self) -> dict:
        """Allowlisted snapshot; never copy the key, endpoint or arbitrary extras."""
        cfg = self.config
        valid = (
            cfg.get("thinking") in {"enabled", "disabled"}
            and isinstance(cfg.get("model"), str)
            and bool(cfg["model"].strip())
            and type(settings.MAX_TOKENS) is int
            and settings.MAX_TOKENS > 0
            and type(cfg.get("max_attempts")) is int
            and 1 <= cfg["max_attempts"] <= 5
        )
        for key in ("temperature", "connect_timeout", "read_timeout"):
            value = cfg.get(key)
            valid = valid and type(value) in (int, float) and math.isfinite(value)
        valid = (
            valid
            and 0 <= cfg["temperature"] <= 2
            and cfg["connect_timeout"] > 0
            and cfg["read_timeout"] > 0
        )
        if not valid:
            raise APIConfigurationError(
                GenerationResult(
                    status="failed",
                    error_code="configuration",
                    error_message="Invalid generation mode, budget, timeout or retry configuration.",
                    requested_model=cfg.get("model"),
                )
            )
        body = {
            "model": cfg["model"],
            "thinking": {"type": cfg["thinking"]},
            "max_tokens": settings.MAX_TOKENS,
            "stream": False,
        }
        if cfg["thinking"] == "disabled":
            body["temperature"] = cfg["temperature"]
        return {
            "protocol": "chat_completions",
            "body": body,
            "connect_timeout_seconds": cfg["connect_timeout"],
            "read_timeout_seconds": cfg["read_timeout"],
            "max_attempts": cfg["max_attempts"],
            "retry_policy": "transient_only_exponential_1_2_4_8_seconds",
        }

    @staticmethod
    def _invalid(metadata):
        return GenerationResult(
            status="failed",
            error_code="invalid_response",
            error_message="API returned an invalid or empty completion.",
            **metadata,
        )

    def generate_result(
        self, prompt: str, *, max_attempts: int | None = None, prepared=None
    ) -> GenerationResult:
        if not isinstance(prompt, str) or not prompt.strip():
            raise ValueError("Prompt must be nonempty text")
        if prepared is not None and prepared.text != prompt:
            raise ValueError("Prompt differs from frozen budgeted request")
        if max_attempts is None:
            max_attempts = self.config["max_attempts"]
        if (
            isinstance(max_attempts, bool)
            or not isinstance(max_attempts, int)
            or not 1 <= max_attempts <= 5
        ):
            raise ValueError("max_attempts must be an integer from 1 to 5")
        started = time.perf_counter()
        history = []
        for attempt in range(max_attempts):
            attempt_started = time.perf_counter()
            try:
                messages = [{"role": "user", "content": prompt}]
                result = (
                    self.send_request(messages, prepared=prepared)
                    if prepared is not None
                    else self.send_request(messages)
                )
            except APIConfigurationError as exc:
                result = exc.result
            if result.request_parameters:
                result = replace(
                    result,
                    request_parameters={
                        **result.request_parameters,
                        "max_attempts": max_attempts,
                    },
                )
            if result.request_sent:
                history.append(
                    {
                        "attempt": attempt + 1,
                        "status": result.status,
                        "error_code": result.error_code,
                        "http_status": result.http_status,
                        "finish_reason": result.finish_reason,
                        "usage": result.usage,
                        "elapsed_seconds": time.perf_counter() - attempt_started,
                        "requested_model": result.requested_model,
                        "returned_model": result.returned_model,
                        "response_id": result.response_id,
                        "reasoning_content_present": result.reasoning_content_present,
                        "reasoning_characters": result.reasoning_characters,
                    }
                )
            if result.completed or not result.retryable or attempt + 1 == max_attempts:
                break
            logger.warning(
                "API attempt failed (%s); retrying %s/%s",
                result.error_code,
                attempt + 2,
                max_attempts,
            )
            time.sleep(min(2**attempt, 8))
        return replace(
            result,
            attempts=len(history),
            elapsed_seconds=time.perf_counter() - started,
            attempt_history=tuple(history),
        )

    def generate_response(self, prompt: str) -> str:
        """Compatibility text interface: incomplete/failed results raise typed errors."""
        return self.generate_result(prompt).require_content()
