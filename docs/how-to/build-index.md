# Build or replace an index

## Build a MiniLM index

Put permitted PDFs in a source directory and choose a new destination. Run from the project root:

```sh
CHEMQA_EMBEDDING_PROFILE= \
CHEMQA_EMBEDDING_MODEL=sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2 \
CHEMQA_EMBEDDING_REVISION=e8f8c211226b894fcb81acc59f3b34ba3efd5f42 \
uv run --locked python -m src.pipeline.vector_index_builder \
  --pdf-dir data/raw_papers --destination output/indexes/my-minilm-candidate
```

The builder stages files, checks identities, source coverage, positions, input lengths, vector alignment, and hashes, then publishes a `ready` candidate. It refuses an existing destination and leaves the active index alone. First use may download weights; no generation request is sent.

Select the new index with `main.py --index-dir output/indexes/my-minilm-candidate`, using the same model/revision and an empty `CHEMQA_EMBEDDING_PROFILE`. The full first-question command is in the [tutorial](../tutorials/first-question.md). Do not combine a rebuilt index with an old frozen runtime profile.

## Build an experimental Qwen index

Use the independent experimental builder; the ordinary builder rejects a Qwen profile:

```sh
HF_HUB_OFFLINE=1 uv run --locked python -m scripts.validate_q065e build \
  --device cpu --batch-size 8
```

This encodes the whole local collection and creates a new candidate. Remove the offline setting only if you need to prepare the pinned model cache. CPU/FP32 and historical MPS/FP16 runs need not have identical rankings.

To migrate that candidate to NumPy/SQLite, explicitly select the directory printed by the builder:

```sh
HF_HUB_OFFLINE=1 uv run --locked python -m scripts.validate_q065f migrate \
  --source output/indexes/YOUR-NEW-QWEN-INDEX
```

Replace the final path with the actual directory. Without `--source`, migration reads the historical source in `docs/Q06_5E_FULL.json`, not necessarily your latest build. Migration preserves the existing text and vectors; it does not re-embed papers.

A binary index alone does not recreate hybrid retrieval or reranking. Those require matching lexical and reranker artifacts and a newly validated runtime configuration. See [retrieval reference](../reference/retrieval.md) for the contracts and [frozen runtimes](frozen-runtime.md) for the original assets.

## Restore a previous index

Select the earlier compatible directory explicitly. Keep its model, revision, and profile paired with it. Never mutate a published candidate or run the old Q01/Q02 migrations repeatedly on current data. Frozen runs can return to `legacy` without deleting candidates.

[Documentation home](../README.md)
