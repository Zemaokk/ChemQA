# Retrieval configurations

The compatibility default is MiniLM/JSON. Experimental candidates remain explicit. The current [R01 runtime manifest](../../config/r01_runtime.json) is the authority for the exact bound local files.

| Setting | Legacy | Hybrid + reranking | Diverse candidate |
| --- | --- | --- | --- |
| Embedding | Multilingual MiniLM L12 v2 | Qwen3-Embedding-0.6B | Same Qwen embedding |
| Dimension | 384 | 1024 | 1024 |
| Full embedding input limit | 128 tokens | 512 tokens | 512 tokens |
| Target chunk overlap | 16 content tokens | 64 tokens, page-local windows | Same |
| Storage | JSON | NumPy float32 + SQLite | Same |
| Retrieval | Exact cosine, top 10; context threshold 0.5 | Dense + BM25, RRF, fixed 50 candidates reranked | Same |
| Final maximum chunks | 10 | 10 | 10 |
| Per-paper cap | No candidate-policy cap | 10 | 6 |
| Span-overlap policy | No candidate selector | Threshold 1.0 | Threshold 0.5 |
| Full serialized request budget | No candidate budget mechanism | 32,000 UTF-8 bytes | Same |

The legacy 0.5 threshold is not calibrated as a probability. BM25, RRF, and reranker logits are different score types and do not use that threshold. Heatmaps show cosine similarity.

Experimental BM25 uses k1=1.2 and b=0.75; each retrieval branch supplies up to 50 entries. RRF uses k=60 with equal weights. The reranker processes the same 50 candidates, with a complete-template 1,024-token limit and batch size 4.

| Model | Pinned revision |
| --- | --- |
| `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` | `e8f8c211226b894fcb81acc59f3b34ba3efd5f42` |
| `Qwen/Qwen3-Embedding-0.6B` | `97b0c614be4d77ee51c0cef4e5f07c00f9eb65b3` |
| `Qwen/Qwen3-Reranker-0.6B` | `e61197ed45024b0ed8a2d74b80b4d909f1255473` |

The query embedding includes its configured instruction; document encoding has its own branch. Length checks include instructions and special tokens and reject silent truncation. The preserved PDF text is cleaned only by whitespace normalization.

Candidate context selection follows frozen order, deduplicates identities/text and configured source overlap, and admits only whole chunks that fit the full request budget. The budget counts serialized HTTP JSON body bytes including metadata and parameters. It is not a provider tokenizer measurement; exact provider input-token count is unknown. Output budget is 4,096 tokens with a 1,024-unit reserve and 40,000-unit total local policy.

The recorded local corpus has 181 PDFs / 180 byte identities, 26,025 legacy chunks, and 6,960 Qwen chunks. These are original local experiment assets, not files supplied by a source checkout.

[Frozen runtime operations](../how-to/frozen-runtime.md) · [Decision to retain the default](../decisions/0004-retain-compatible-default.md) · [Documentation home](../README.md)
