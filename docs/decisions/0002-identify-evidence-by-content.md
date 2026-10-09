# 0002. Identify evidence by content

Date: 2026-10-09  
Status: Accepted (retrospective record of an existing decision)

## Context

Local chunk numbers collided across PDFs and could map a citation to the wrong document. Filenames are aliases rather than stable identities, and an answer needs a source location beyond a document title.

## Decision

Use PDF-byte SHA-256 for document identity and a versioned document/index/exact-text tuple for chunk identity. Carry physical PDF pages and exact extracted-text intervals into the index, retrieval, prompt record, and citation map. Preserve unresolved references explicitly.

## Alternatives

Filename-only identities change on rename. Local chunk indexes are not globally unique. DOI alone cannot distinguish PDF versions or anchor exact extracted text. Inferring unavailable pages would fabricate provenance.

## Consequences

Renamed identical PDFs retain identity, while edited bytes and changed chunks receive new IDs. Different PDF versions of the same article need separate mappings. Exact-text spans support auditing but do not guarantee faithful equations or layout coordinates.

Evidence: [Artifact contracts](../reference/artifact-contracts.md), [Q01 validation](../Q01_VALIDATION.json), and [Q02 validation](../Q02_VALIDATION.json).

[Decision index](README.md)
