# 0005. Isolate rejected answers

Date: 2026-10-09  
Status: Accepted (retrospective record of an existing decision)

## Context

Transport success and resolved citations do not establish answer reliability. Recorded failures included equation reconstruction, condition mixing, and unsupported absence claims. Error strings and partial outputs must not be published as complete answers.

## Decision

The current QA entry point uses a conservative R01 prompt and limited lexical answer checks. Save failed, truncated, and validation-rejected generations separately with diagnostics; do not publish normal answer files or automatically retry an answer-check rejection. Preserve successful and local no-evidence runs with explicit states.

## Alternatives

Publishing any HTTP-success text would hide known failure classes. Automatically regenerating rejected answers would add uncontrolled attempts. Treating lexical checks as a semantic scientific verifier would exceed their implementation.

## Consequences

Failures remain inspectable and cannot overwrite another run. Checks have false positives and false negatives, and current delivery can be poor: P3 rejected 78/90 RAG outputs. Historical evaluation generators retain old behavior. Any guard revision requires new evaluation of both scientific errors and actual delivery.

Evidence: [Reliability explanation](../explanation/answer-reliability.md), [R01 validation](../R01_VALIDATION.json), and [P3 execution](../P3_EXECUTION_VALIDATION.json).

[Decision index](README.md)
