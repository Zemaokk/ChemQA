# CLI and configuration

## Main entry point

`uv run --locked python main.py [options]`

| Option | Meaning |
| --- | --- |
| `-q`, `--question TEXT` | One question; without it, start an interactive session. |
| `--index-dir PATH` | Select the index and processed-data directory. |
| `--output-dir PATH` | Root for isolated run directories. |
| `--runtime-profile NAME` | `legacy`, `hybrid_rerank`, or `hybrid_rerank_diverse`. |
| `--check-runtime` | Verify a selected profile's files and exit without model loading or HTTP. Requires `--runtime-profile`. |

`--index-dir` and `--runtime-profile` are mutually exclusive. Single-question generation failure exits with code 1. Interactive sessions accept `exit` and `quit`.

## Index builder

`uv run --locked python -m src.pipeline.vector_index_builder [options]`

| Option | Meaning |
| --- | --- |
| `--pdf-dir PATH` | Source PDFs; defaults to the configured raw-paper directory. |
| `--destination PATH` | New candidate directory; existing targets are refused. |
| `--output-dir PATH` | Root for automatically named candidates. |

The ordinary builder supports the MiniLM path. Experimental Qwen builds use `scripts.validate_q065e build`.

## Environment

Explicit shell values override `.env`; CLI path flags override configured paths. Relative paths and `~` are resolved by the project settings. The project-root `.env` is loaded independently of the launch directory.

| Variable | Default / behavior |
| --- | --- |
| `DEEPSEEK_API_KEY` | Empty; required for nonempty-evidence generation. |
| `DEEPSEEK_BASE_URL` | `https://api.deepseek.com`; client appends `/chat/completions`. |
| `DEEPSEEK_MODEL` | `deepseek-flash`. |
| `DEEPSEEK_TEMPERATURE` | `0.3`. |
| `DEEPSEEK_THINKING` | `disabled`; provider compatibility must be checked. |
| `DEEPSEEK_MAX_TOKENS` | `4096`. |
| `DEEPSEEK_CONNECT_TIMEOUT` | `10` seconds. |
| `DEEPSEEK_READ_TIMEOUT` | `120` seconds. |
| `DEEPSEEK_MAX_ATTEMPTS` | `3` total attempts for ordinary generation; frozen profiles use their manifest. |
| `CHEMQA_EMBEDDING_MODEL` | `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`. |
| `CHEMQA_EMBEDDING_REVISION` | Pinned MiniLM revision `e8f8c211226b894fcb81acc59f3b34ba3efd5f42` for that default model. |
| `CHEMQA_EMBEDDING_PROFILE` | Unset; optional pinned experimental profile. |
| `CHEMQA_RAW_PAPERS_DIR` | `data/raw_papers`. |
| `CHEMQA_INDEX_DIR` | `data/vector_db`. |
| `CHEMQA_PROCESSED_DIR` | `data/processed`; follows an explicitly selected environment index if not separately set. CLI `--index-dir` sets both. |
| `CHEMQA_OUTPUT_DIR` | `output`. |
| `CHEMQA_MODEL_DIR` | `models`. |
| `HF_HOME` | Hugging Face cache location; `.env.example` sets `models/huggingface`. |
| `HF_HUB_OFFLINE` | Optional `1` to prohibit model downloads after caching. |
| `MPLBACKEND` | Optional `Agg` for plots without a display. |

Frozen profiles replace retrieval and generation settings from their manifest, retaining the externally supplied key and optional CLI output root. See [profile reference](retrieval.md).

Dependency source: `pyproject.toml`; exact resolution: `uv.lock`; generated runtime-only export: `requirements.txt`. Python is constrained to `>=3.12,<3.13`.

[Documentation home](../README.md)
