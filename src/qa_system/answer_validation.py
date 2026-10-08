"""Narrow lexical safety checks; passing does not certify scientific support."""

import re
import unicodedata
from decimal import Decimal

from config.answer_policy import ANSWER_POLICY_VERSION
from src.qa_system.evidence import resolve_citations

SCOPES = {
    "potential": r"电位|电压|potential|voltage|overpotential",
    "current": r"电流|current",
    "rate": r"产率|生产速率|productivity|production rate|yield rate",
    "efficiency": r"法拉第|选择性|收率|\bFE\b|efficiency|selectivity|yield",
    "concentration": r"浓度|电解液|摩尔比|当量|concentration|electrolyte|ratio|equiv|loading",
    "temperature": r"温度|temperature",
    "time": r"时间|多久|稳定|duration|stability|how long|time",
}
UNITS = {
    "mV": "potential",
    "V": "potential",
    "mA": "current",
    "A": "current",
    "μmol": "rate",
    "mmol": "rate",
    "%": "efficiency",
    "mol%": "concentration",
    "mol": "concentration",
    "mM": "concentration",
    "M": "concentration",
    "equiv": "concentration",
    "°C": "temperature",
    "K": "temperature",
    "min": "time",
    "h": "time",
    "s": "time",
}
QUANTITY = re.compile(
    r"(?<![A-Za-z0-9_.+−-])(?P<value>[+−-]?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)\s*"
    r"(?P<unit>mol%|(?:μmol|mmol|mA|A)"
    r"(?:(?:\s*cm\s*\^?\s*-?2)|(?:\s*/\s*cm\^?2))?"
    r"(?:\s*h\s*\^?\s*-1)?"
    r"|equiv|mM|mV|min|°\s*C|V|M|mol|%|K|h|s)(?![A-Za-z])"
)
ABSENCE = re.compile(
    r"(?:全文|整篇论文|整个语料).{0,16}(?:没有|不存在|未报告|未提供)"
    r"|(?:原文|论文).{0,8}(?:没有|不存在).{0,8}(?:对照|证据)"
    r"|(?:paper|article)\s+(?:contains no|has no)\s+(?:controls?|evidence)"
    r"|no control experiments?\s+(?:exist|were performed)",
    re.IGNORECASE,
)
SCOPED = re.compile(
    r"当前片段|检索片段|本次证据|provided (?:excerpts|context)|retrieved (?:excerpts|context)",
    re.IGNORECASE,
)
ANOMALY = re.compile(
    r"原文异常|需(?:要)?核查|疑似错误|不能按有效|source anomaly|requires verification",
    re.IGNORECASE,
)


def normalized(text):
    return unicodedata.normalize("NFKC", text).replace("−", "-")


def quantities(text):
    for match in QUANTITY.finditer(normalized(text)):
        unit = re.sub(r"\s+", "", match["unit"])
        unit = unit.replace("^", "").replace("/cm2", "cm-2")
        yield (Decimal(match["value"].replace("−", "-")), unit)


def requested_scopes(question):
    if re.search(
        r"条件|性能|数值|参数|conditions?|performance|parameters?|metrics?",
        question,
        re.IGNORECASE,
    ):
        return set(SCOPES)
    return {
        name
        for name, pattern in SCOPES.items()
        if re.search(pattern, question, re.IGNORECASE)
    }


def audit_answer(question, answer, chunks):
    findings = []
    allowed = requested_scopes(question)
    by_id = {c["chunk_id"]: c for c in chunks}
    resolved = resolve_citations(answer, chunks, allow_legacy=False)
    if resolved["unresolved"]:
        findings.append(
            {"code": "unresolved_citation", "markers": resolved["unresolved"]}
        )
    for paragraph in re.split(r"\n\s*\n", answer):
        ids = re.findall(r"\[Ref (chunk_[a-f0-9]{64})\]", paragraph)
        cited = [by_id[cid]["text"] for cid in ids if cid in by_id]
        supported = {q for text in cited for q in quantities(text)}
        for value, unit in quantities(paragraph):
            scope = next(UNITS[prefix] for prefix in UNITS if unit.startswith(prefix))
            if scope not in allowed:
                findings.append(
                    {"code": "unrequested_quantity", "value": str(value), "unit": unit}
                )
            if (value, unit) not in supported:
                findings.append(
                    {
                        "code": "quantity_not_in_cited_excerpt",
                        "value": str(value),
                        "unit": unit,
                    }
                )
        for sentence in re.split(r"[。！？;；\n]|(?<!\d)\.(?!\d)", paragraph):
            if (
                re.search(
                    r"\bFE\b|efficiency|selectivity|选择性|收率|效率",
                    sentence,
                    re.IGNORECASE,
                )
                and not re.search(
                    r"变化|下降|降低|change|decreas|relative|delta|百分点",
                    sentence,
                    re.IGNORECASE,
                )
                and any(
                    value < 0 and unit == "%" for value, unit in quantities(sentence)
                )
                and not ANOMALY.search(sentence)
            ):
                findings.append(
                    {"code": "unflagged_negative_percentage", "text": sentence.strip()}
                )
            if ABSENCE.search(sentence) and not SCOPED.search(sentence):
                findings.append(
                    {"code": "unbounded_evidence_absence", "text": sentence.strip()}
                )
        for line in paragraph.splitlines():
            if not re.search(r"→|⟶|->|\\(?:long)?rightarrow", line) or not re.search(
                r"[+•·]|\\(?:bullet|cdot)", line
            ):
                continue
            formula = re.sub(r"\[Ref [^\]]+\]", "", line).strip().strip("`$")
            formula = re.sub(r"^\s*(?:[-*]|\d+\.)\s+", "", formula)
            compact = "".join(formula.split())
            asked = re.search(
                r"方程|反应式|equation|reaction scheme", question, re.IGNORECASE
            )
            # Do not normalize charges or signs: that would hide extraction damage.
            if (
                not asked
                or not compact
                or not any(compact in "".join(t.split()) for t in cited)
            ):
                findings.append(
                    {"code": "unverified_reaction_equation", "text": line.strip()}
                )
    return {
        "schema": "chemqa-answer-validation-v1",
        "policy": ANSWER_POLICY_VERSION,
        "status": "blocked" if findings else "passed_lexical_checks",
        "findings": findings,
        "scientific_support_verified": False,
    }
