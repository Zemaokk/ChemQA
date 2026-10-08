"""Deterministic handling of absent retrieval evidence; no semantic sufficiency guess."""

EVIDENCE_POLICY_VERSION = "chemqa-evidence-boundary-v1"

NO_EVIDENCE_ANSWER = """### 体系与证据适用性
当前证据不足。本次检索未返回符合筛选条件的证据片段，无法据此判断所问体系的机理、性能、最佳条件或应用前景。

### 可支持的结论
当前检索证据不足以回答目标体系的问题。检索为空不等于相关文献不存在，也不是对所问主张的反证；这里不使用其他体系类比来补写结论。

### 下一步核查
请明确反应物与目标产物、催化剂、电解液、反应器构型及相关操作条件，或提供可核查的同体系文献后再分析。"""


def generation_decision(chunks: list[dict]) -> dict:
    """Nonempty retrieval means candidate evidence, not verified scientific support."""
    return {
        "policy_version": EVIDENCE_POLICY_VERSION,
        "evidence_availability": "retrieved_not_assessed" if chunks else "none",
        "route": "model_request" if chunks else "local_no_evidence",
        "scientific_support_verified": False,
    }
