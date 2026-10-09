# Current status and next work

Status consolidated on 2026-10-09. This is a working summary, not a release announcement.

Implemented: stable document/chunk identity, physical-page/source-span tracing, tokenizer-aware input checks, shared cosine scoring, normalized evidence prompts, explicit API results, isolated output/index publication, external credentials, experimental Qwen retrieval/storage/reranking, frozen runtime profiles, and conservative answer checks.

The compatibility default remains MiniLM/JSON. Hybrid/reranking and diversity selection are explicit candidates. PyMuPDF remains the parser; Docling migration and FAISS were not adopted. These choices and their tradeoffs are captured in [ADRs](../decisions/README.md).

Q10-B generation and review are complete as an exploratory comparison, with consumed reserved questions and recorded scientific errors. R01 engineering checks passed in their recorded validation. P3 completed 180 generations and initial scoring, exposing a high publication-rejection rate; key adjudications remain unresolved. There is no default switch or completed independent scientific acceptance.

Next work, in order:

1. Resolve the P3 scoring and source-attribution disputes without overwriting initial scores.
2. Open a separate revision for requested-metric recognition and excessive answer expansion. Preserve the existing R01 experiment.
3. Improve extraction fidelity for signs, charges, formulas, and condition attribution.
4. Freeze a new evaluation with unused questions and comparable configurations. Report raw and delivered scores together.

Changes to implementation or an adopted default need a new validation record and, where architecturally significant, a new ADR. Document restructuring alone does not change model behavior or historical results.

[Changelog](../../CHANGELOG.md) · [Documentation home](../README.md)
