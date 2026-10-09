# Run batch utilities and similarity plots

## Inspect batch options

```sh
uv run --locked python -m qa_testing.test_organic_electrocatalysis_qa --help
uv run --locked python -m qa_testing.direct_api_test --help
```

Help does not send requests. Running these utilities does: the first asks the preset questions with retrieval, while the second exercises direct API generation. They are historical usage checks rather than a controlled scientific comparison.

The RAG utility accepts `--index-dir` and `--output-dir` and reads environment configuration. It has no frozen `--runtime-profile` switch. Select the matching embedding model/revision for your index before running it. New sessions go to `output/qa_batches/` or `output/direct_api_batches/`; failures are saved separately.

A session marked `complete` has finished writing its summary. Read the success, failure, truncation, no-evidence, and pending counts before interpreting it. A historical answer with no explicit status is `unverified`, not implicitly successful.

## Generate a local similarity heatmap

With the default JSON index and model cache ready:

```sh
HF_HUB_OFFLINE=1 MPLBACKEND=Agg uv run --locked python -m heatmap_visualization.run_heatmap
```

The plot is written under `output/heatmaps/<run-id>/`. It uses stored document vectors and encodes the queries locally without calling the generation API. Single-query ranking matches cosine retrieval; multi-query plots select rows using mean cosine scores. Color measures vector similarity, not scientific support probability.

[Run layout](../reference/artifact-contracts.md) · [Documentation home](../README.md)
