# Diagnose a failed run

Start with command parsing, then local assets, then the recorded generation status:

```sh
uv run --locked python main.py --help
uv run --locked python -m scripts.smoke_check
```

The smoke check requires at least one local PDF and does not call the generation API. With the default JSON index and cache ready, add a local retrieval check:

```sh
HF_HUB_OFFLINE=1 uv run --locked python -m scripts.smoke_check --retrieval
```

This is not a binary/hybrid candidate acceptance test.

| Symptom | Action |
| --- | --- |
| Missing PDF or index | Supply permitted PDFs and [build a new index](build-index.md), or restore the original matching archive. |
| Offline model load fails | Prepare the pinned revision's cache. `HF_HUB_OFFLINE=1` prevents downloads; installing packages does not install weights. |
| Frozen file missing or changed | Compare the manifest with the local asset. Restore it or validate a new runtime; do not silently replace its expected hash. |
| Frozen model shadow directory | Remove the unintended local override from model selection or use the intended pinned Hub cache; preserve any needed files separately. |
| Profile/index mismatch or index not ready | Select a matching pair. A candidate must be published and pass hash checks. |
| Query exceeds model input limit | Shorten the question. The encoder rejects it instead of silently truncating. |
| Authentication failure | Check the external key and endpoint/model pair. Never copy the key into a bug report. |
| Timeout, HTTP failure, or truncation | Inspect `failure.json` and attempt history. A partial response is diagnostic content. |
| `answer_validation` failure | Inspect findings and cited text, then narrow the question or review the raw response. Checks can reject valid phrasing; no automatic retry is triggered. |
| Citation resolves but result looks wrong | Inspect the PDF page, especially signs, charges, units, and experiment attribution. |

For code changes, run the checks in [CONTRIBUTING](../../CONTRIBUTING.md). For field definitions, see [artifact contracts](../reference/artifact-contracts.md).

[Documentation home](../README.md)
