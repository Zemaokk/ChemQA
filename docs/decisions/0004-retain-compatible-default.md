# 0004. Retain the compatible default

Date: 2026-10-09  
Status: Accepted (retrospective record of an existing decision)

## Context

Qwen retrieval candidates improved labeled development-anchor coverage. Q10-B showed scored core-point coverage but also additional scientific errors, and did not compare legacy MiniLM generation under the same conditions. P3 later exposed high R01 publication rejection.

## Decision

Retain MiniLM/JSON as the compatibility default. Offer hybrid/reranking and diversity selection through explicit bound local profiles. Keep rollback available without deleting candidate assets. Treat later improvements as separately validated revisions.

## Alternatives

Switching the default based on development recall or required-point scores would conflate retrieval coverage with complete answer quality. Enabling every new component would ignore the diversity-selection recall regression. Retaining the default is not evidence that it is scientifically superior.

## Consequences

Users can choose and audit experimental paths while ordinary compatibility is preserved. More than one pipeline needs maintenance. A default switch needs new comparable evidence; consumed evaluation questions cannot become independent tests again.

Evidence: [Retrieval reference](../reference/retrieval.md), [Q10-B scores](../Q10B_EXPERT_RESULTS.json), and [P3 results](../P3_RESULTS.json).

[Decision index](README.md)
