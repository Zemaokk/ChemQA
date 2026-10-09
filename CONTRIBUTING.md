# Contributing

Bug reports should include the command, configuration, run status, and a minimal reproducible example. For answer-quality issues, identify the claim and the source passage it does or does not follow from. Share excerpts only where permitted and remove credentials from logs.

Use Python 3.12 and the locked environment:

```sh
uv sync --locked
uv run --locked ruff check .
uv run --locked ruff format --check .
HF_HUB_OFFLINE=1 MPLBACKEND=Agg uv run --locked python -m unittest discover -s tests
```

Offline runs require the relevant caches. Prefer synthetic fixtures. Preserve existing experiment inputs, scores, and consumption markers; new behavior needs new validation rather than relabeling old results.

Dependencies are declared in `pyproject.toml` and resolved in `uv.lock`. Regenerate the runtime-only export with:

```sh
uv export --locked --no-dev --format requirements-txt --no-hashes --output-file requirements.txt
```

Documentation changes follow [the maintenance guide](docs/how-to/maintain-documentation.md). Significant design changes need an [ADR](docs/decisions/README.md); notable user-facing changes belong in [CHANGELOG.md](CHANGELOG.md). The [file policy](docs/reference/repository-policy.md) defines what can enter source control.
