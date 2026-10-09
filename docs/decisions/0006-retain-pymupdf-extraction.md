# 0006. Retain PyMuPDF extraction

Date: 2026-10-09  
Status: Accepted (retrospective record of an existing decision)

## Context

Extracted-text offsets must remain verifiable against a known source. A ten-page parser comparison found some Docling table benefits but did not satisfy source-mapping, formula, and OCR migration requirements.

## Decision

Keep PyMuPDF `get_text("text", sort=False)` as the indexed text source. Keep alternative parsing experiments isolated rather than reparsing the collection or enabling full-corpus OCR by default.

## Alternatives

A full Docling migration would change text, identities, locations, and indexes together without adequate migration validation. A low-text/image heuristic is insufficient evidence that every page needs or does not need OCR.

## Consequences

Current source spans remain reproducible under their extractor contract, and the primary dependency environment stays stable. Reading order and damaged scientific notation remain known limitations. Parser changes need a new corpus/version and page-level fidelity validation.

Evidence: [Architecture](../explanation/architecture.md), [sample protocol](../Q06_5D_SAMPLE.json), [parser runtime](../Q06_5D_RUNTIME.json), and [review records](../Q06_5D_REVIEW.json).

[Decision index](README.md)
