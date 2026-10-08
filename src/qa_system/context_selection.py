"""Deterministic whole-chunk selection and a frozen, conservative request budget.

UTF-8 bytes are an auditable admission estimate, not provider tokenization.
No inferred semantic support or cosine threshold is applied to reranker logits.
"""

import hashlib
import json
from dataclasses import dataclass, replace

from src.api_integration.prompt_builder import PreparedPrompt, prepare_prompt
from src.qa_system.context import normalize_context


def digest(value):
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True).encode()
    ).hexdigest()


def validate_policy(policy):
    if policy.get("schema") != "chemqa-context-selection-v1":
        raise ValueError("Invalid context selection policy")
    for key in [
        "candidate_window",
        "max_chunks",
        "max_chunks_per_document",
        "input_estimate_limit",
        "output_token_limit",
        "protocol_token_reserve",
        "total_estimate_limit",
    ]:
        if type(policy.get(key)) is not int or policy[key] <= 0:
            raise ValueError("Context budget/count must be positive integers")
    overlap = policy.get("maximum_existing_span_overlap")
    if (
        type(overlap) not in (int, float)
        or not 0 <= overlap <= 1
        or policy["candidate_window"] != 50
        or policy["max_chunks"] > 50
        or policy["max_chunks_per_document"] > policy["max_chunks"]
        or policy.get("counter") != "complete-payload-utf8-bytes-v1"
        or policy.get("selection_order") != "frozen_retrieval_rank"
        or policy.get("neighbor_expansion") is not False
        or policy["input_estimate_limit"]
        + policy["output_token_limit"]
        + policy["protocol_token_reserve"]
        > policy["total_estimate_limit"]
    ):
        raise ValueError("Unsupported or inconsistent context budget policy")


def payload_for(prepared, body):
    return {**body, "messages": [{"role": "user", "content": prepared.text}]}


def request_size(prepared, body):
    # Same JSON serialization defaults as requests' json= payload, including escaping.
    # ensure_ascii=True also counts serialized non-ASCII escapes conservatively.
    return len(json.dumps(payload_for(prepared, body), allow_nan=False).encode("utf-8"))


def verify_budget(prepared, body):
    record = prepared.budget
    if record is None:
        raise ValueError("Missing frozen request budget")
    policy = record["policy"]
    validate_policy(policy)
    size = request_size(prepared, body)
    if (
        record.get("schema") != "chemqa-request-budget-v1"
        or record.get("policy_sha256") != digest(policy)
        or record["request_body"] != body
        or record["payload_sha256"] != digest(payload_for(prepared, body))
        or size != record["input_estimate"]
        or size > policy["input_estimate_limit"]
        or body.get("max_tokens") != policy["output_token_limit"]
        or record["total_estimate"]
        != size + policy["output_token_limit"] + policy["protocol_token_reserve"]
        or size + policy["output_token_limit"] + policy["protocol_token_reserve"]
        > policy["total_estimate_limit"]
    ):
        raise ValueError("Request changed or exceeds frozen generation budget")
    return record


def span_overlap(chunk, selected):
    """Fraction of this chunk's located source characters already supplied."""
    if chunk.get("location_status") != "located":
        return 0.0
    spans = chunk["source_spans"]
    total = sum(s["char_end"] - s["char_start"] for s in spans)
    if total <= 0:
        return 0.0
    covered = 0
    for span in spans:
        intervals = []
        for prior in selected:
            if (
                prior["doc_id"] != chunk["doc_id"]
                or prior.get("location_status") != "located"
            ):
                continue
            for old in prior["source_spans"]:
                if old["page_number"] == span["page_number"]:
                    a = max(span["char_start"], old["char_start"])
                    b = min(span["char_end"], old["char_end"])
                    if b > a:
                        intervals.append((a, b))
        end = -1
        for a, b in sorted(intervals):
            covered += max(0, b - max(a, end))
            end = max(end, b)
    return covered / total


@dataclass(frozen=True)
class ContextSelection:
    prepared: PreparedPrompt
    audit_json: str

    @property
    def audit(self):
        return json.loads(self.audit_json)


def select_context(question, hits, policy, body, *, template=None):
    validate_policy(policy)
    if len(hits) > policy["candidate_window"]:
        raise ValueError("Candidate window cannot expand beyond frozen 50")
    if body.get("max_tokens") != policy["output_token_limit"]:
        raise ValueError("Generation output budget differs from selection policy")
    # Validate every ID/location first, including candidates that might be excluded.
    normalized = [normalize_context([h["document"]])[0] for h in hits]
    # Merge aliases and reject conflicting located metadata before deduplication.
    canonical = {c["chunk_id"]: c for c in normalize_context(normalized)}
    normalized = [canonical[c["chunk_id"]] for c in normalized]
    kwargs = {} if template is None else {"template": template}
    prepared = prepare_prompt(question, [], **kwargs)
    if request_size(prepared, body) > policy["input_estimate_limit"]:
        raise ValueError("Question/template alone exceeds generation input budget")
    selected, records = [], []
    seen_ids, seen_texts = set(), set()
    for rank, chunk in enumerate(normalized, 1):
        text_hash = hashlib.sha256(" ".join(chunk["text"].split()).encode()).hexdigest()
        overlap = span_overlap(chunk, selected)
        reason = None
        if chunk["chunk_id"] in seen_ids:
            reason = "duplicate_chunk_id"
        elif text_hash in seen_texts:
            reason = "duplicate_text"
        elif overlap > policy["maximum_existing_span_overlap"]:
            reason = "source_span_overlap"
        elif len(selected) >= policy["max_chunks"]:
            reason = "chunk_limit"
        elif (
            sum(c["doc_id"] == chunk["doc_id"] for c in selected)
            >= policy["max_chunks_per_document"]
        ):
            reason = "document_limit"
        else:
            proposal = prepare_prompt(question, [*selected, chunk], **kwargs)
            if request_size(proposal, body) > policy["input_estimate_limit"]:
                reason = "input_budget"
            else:
                selected.append(chunk)
                prepared = proposal
        seen_ids.add(chunk["chunk_id"])
        seen_texts.add(text_hash)
        records.append(
            {
                "rank": rank,
                "chunk_id": chunk["chunk_id"],
                "doc_id": chunk["doc_id"],
                "selected": reason is None,
                "reason": reason,
                "overlap_with_selected": overlap,
            }
        )
    size = request_size(prepared, body)
    budget = {
        "schema": "chemqa-request-budget-v1",
        "policy": dict(policy),
        "policy_sha256": digest(policy),
        "request_body": dict(body),
        "input_estimate": size,
        "output_token_reserve": policy["output_token_limit"],
        "protocol_token_reserve": policy["protocol_token_reserve"],
        "total_estimate": size
        + policy["output_token_limit"]
        + policy["protocol_token_reserve"],
        "provider_exact_input_tokens": None,
        "counter_is_provider_tokenizer": False,
        "payload_sha256": digest(payload_for(prepared, body)),
    }
    prepared = replace(prepared, budget_json=json.dumps(budget, ensure_ascii=False))
    verify_budget(prepared, body)
    audit = {
        "schema": "chemqa-context-selection-audit-v1",
        "policy_sha256": digest(policy),
        "candidate_count": len(hits),
        "selected_count": len(selected),
        "selected_document_count": len({c["doc_id"] for c in selected}),
        "records": records,
        "empty_selection_reason": "no_candidates"
        if not hits
        else ("no_whole_chunk_fits_policy" if not selected else None),
        "scientific_support_verified": False,
        "neighbor_expansion_count": 0,
    }
    return ContextSelection(prepared, json.dumps(audit, ensure_ascii=False))
