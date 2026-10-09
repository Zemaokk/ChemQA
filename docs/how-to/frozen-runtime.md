# Verify, select, or roll back a frozen runtime

These steps require the original local experiment assets. A source checkout alone cannot reconstruct them. The current CLI reads [the R01 manifest](../../config/r01_runtime.json).

## Verify files before use

```sh
uv run --locked python main.py --runtime-profile legacy --check-runtime
uv run --locked python main.py --runtime-profile hybrid_rerank --check-runtime
uv run --locked python main.py --runtime-profile hybrid_rerank_diverse --check-runtime
```

These commands verify bound files without loading models or calling the API. They do not establish that the model cache can load, that a provider is available, or that an answer will be correct.

## Select a profile

```sh
uv run --locked python main.py --runtime-profile hybrid_rerank \
  --output-dir output/manual-candidate \
  -q "What evidence supports this reaction mechanism?"
```

This sends a real request for nonempty evidence. The profile fixes retrieval and generation settings, including the provider endpoint; it uses your external key. Omit `-q` for interactive mode. Do not pass `--index-dir` alongside a profile.

## Roll back to the compatibility configuration

```sh
uv run --locked python main.py --runtime-profile legacy --check-runtime
uv run --locked python main.py --runtime-profile legacy \
  -q "What is organic electrocatalysis?"
```

Candidates remain available. `legacy` refers to the retrieval configuration; the current CLI still uses R01 answer checks.

## Handle drift

For `Frozen runtime file missing or changed`, restore the matching asset or validate a new configuration. Do not edit an old expected hash and call the result the same experiment. Keep PDFs, pinned model caches, indexes, raw answers, and generation inputs in a separate permitted archive.

The old J manifest records the pre-R01 implementation. Its source hashes are expected to fail against current R01 code. Replaying that behavior requires a separate checkout of `6df5c64` and its original assets. Current documentation migration does not change those experimental records.

[Retrieval profiles](../reference/retrieval.md) · [Documentation home](../README.md)
