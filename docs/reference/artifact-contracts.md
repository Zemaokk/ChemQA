# Evidence, indexes, and run artifacts

## Document and chunk identity

Identity version: `sha256-pdf-chunk-v1`.

- `doc_id` is `doc_` plus SHA-256 of the original PDF bytes. Renaming identical bytes preserves identity; a different PDF version changes it even with the same DOI.
- `chunk_id` is `chunk_` plus SHA-256 of the serialized identity-version, document-ID, local-index, and exact-text tuple. Local chunk numbers are not global keys.
- Duplicate identities retain source aliases. Text or chunking changes create new chunk identities.
- Generation citations use `[Ref <full chunk_id>]`. Displayed numeric references are answer-local formatting. Unknown or ambiguous markers remain unresolved rather than being assigned by guesswork.

## Source locations

Location version: `pymupdf-text-offset-v1`.

| Field | Meaning |
| --- | --- |
| `location_status` | `located` or `unavailable`; unavailable locations carry a reason. |
| `page_numbers` | One-based physical PDF pages contributing evidence. |
| `source_spans` | Page number, `char_start`, `char_end`, and extracted `raw_text`. |
| `[char_start, char_end)` | Half-open Unicode character offsets in that page's `get_text('text', sort=False)` string. |
| `location_extractor` | Recorded extractor/version/method. |

These are not PDF byte offsets, printed page labels, or highlight coordinates. Raw extracted text can already contain formula or reading-order errors.

## Prompt evidence

`chemqa-evidence-v1` serializes evidence as JSON with an evidence count and normalized records containing citation, chunk/document IDs, source title, location status, pages, and exact chunk text. The prepared prompt and evidence snapshot used for generation are retained in the run record. Evidence is source data, not instructions.

Empty evidence takes the local `no_evidence` route. Nonempty evidence is recorded as `retrieved_not_assessed`; `scientific_support_verified` remains false. The current guarded generator uses the conservative R01 prompt. Historical evaluation generators retain their own prompt versions.

## QA run layout

```text
output/qa/<UTC-timestamp-UUID>/
  run.json
  answer.md                 # success or local no_evidence
  answer.evidence.json
  citation_analysis.txt     # when applicable
  failure.json              # failed/truncated; replaces normal answer files
```

A custom output root retains the `qa/<run-id>/` suffix. `answer.evidence.json` records question, raw answer, generation input/result, evidence mapping, and unresolved citations. R01 validation diagnostics are under `generation_input.answer_validation`.

| Generation status | Meaning |
| --- | --- |
| `success` | Complete, nonempty response with an accepted completion shape and stop reason; not a scientific correctness label. |
| `no_evidence` | Local response, no generation request. |
| `failed` | Configuration, transport, response-protocol, or answer-validation failure. |
| `truncated` | Output ended at the generation length limit. |

`GenerationResult` records available usage, finish reason, requested/returned model, response ID, attempt history, error class, and request status. Missing usage is not zero. Partial content is diagnostic, not a complete answer. Compatibility text APIs raise `APIGenerationError` for incomplete results.

Ordinary requests retry selected transient failures within the total attempt limit: HTTP 429/500/502/503/504, network/timeout errors, and insufficient-resource responses. Permanent errors, malformed responses, truncation, and R01 answer rejections are not automatically retried.

## Index layouts

| Index | Files |
| --- | --- |
| MiniLM JSON candidate | `vector_index.json`, `processed_chunks.json`, `run.json` |
| Experimental binary candidate | `vectors.npy`, `metadata.sqlite3`, `storage.json`, `run.json` |

Published candidates are `ready`, hash-checked, and immutable. Binary storage preserves float32 rows and complete chunk metadata, uses read-only memory mapping and SQLite, and validates shape, values, identities, and model compatibility. It does not silently fall back to JSON in the same directory.

Single QA, index, and plot artifacts stage files before publication. Batch sessions start as `running` and become `complete` after summaries are saved; inspect their per-result counts. This is not a cross-process transaction or a power-loss durability guarantee.

[Retrieval](retrieval.md) · [Documentation home](../README.md)
