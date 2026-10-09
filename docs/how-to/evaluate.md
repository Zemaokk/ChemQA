# Validate and replay an evaluation

## Inspect existing results

Start with [evaluation results](../explanation/evaluation-results.md), then use the [record catalog](../reference/experiment-records.md) to locate the protocol, inputs, execution checks, and scoring records. Keep Q10-B and P3 results separate: they use different questions, rubrics, prompts, and aggregation.

## Check source anchors without generation

With the original permitted PDFs available:

```sh
uv run --locked python -m scripts.validate_q10a \
  --dataset-dir evaluation/q10b --report /tmp/chemqa-q10b-source-check.json
```

This verifies dataset hashes, PDF identities, physical pages, and exact text spans. It does not encode reserved queries or call the generation API. Exact matching does not adjudicate scientific interpretation.

## Replay the original Q10-B preview

Restore the original local preview, then run:

```sh
HF_HUB_OFFLINE=1 uv run --locked python -m scripts.validate_q10b replay \
  --candidate output/q10b_previews/20261008T003102-7049b4e82a524fcabd2ff19c61501b35
```

This checks saved inputs, prompts, and budgets without a new ranking or HTTP request. It writes `docs/Q10B_REPLAY.json`; inspect changes before accepting a new record. Do not replace missing historical previews with new reserved-set retrievals.

The `report` subcommand reads historical generations and writes a review package and engineering summary. It does not merge the separate scored review layer and is not needed merely to read the results. Other stage validators may re-encode development queries or write fixed report paths; inspect `--help` and the [catalog](../reference/experiment-records.md) before running them.

## Start a new comparison

Use new unused questions, predefine accepted answers and source anchors, and freeze the split, candidate configuration, prompts, budgets, retries, scoring denominator, and aggregation before generation. Record raw responses, failures, and publication-check results separately. Append adjudications with reasons and versions instead of silently rewriting earlier scores.

The Q10-B reserve and P3 questions have already been consumed. Preserve their consumption markers and original answers. Earlier request approval applies only to its recorded input scope; prepare and review the exact new excerpt scope before new third-party generation.

[Metrics and protocols](../reference/evaluation.md) · [Documentation home](../README.md)
