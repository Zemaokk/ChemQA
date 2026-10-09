# Prepare and share a source snapshot

Keep secrets in the ignored `.env`, and keep papers, indexes, weights, and generated answers outside the source package. The development history still contains old credentials recorded as revoked; source sharing uses a fresh snapshot without Git history.

## Check and prepare

```sh
uv run --locked python -m scripts.audit_secrets
uv run --locked python -m scripts.audit_secrets --staged
uv run --locked python -m scripts.prepare_source_release
```

These commands scan the defined credential patterns and create a local snapshot under `output/source_releases/`. They do not publish or push it. Pattern scanning has a defined text/size scope and cannot prove comprehensive absence of secrets.

## Review the prepared files

Check `SOURCE_RELEASE.json` and the actual files. The snapshot excludes Git history, local environment, papers, weights, indexes, generated outputs, and `legacy-docs/`. It includes the current documentation, changelog, contribution guide, and small machine records.

Documentation and evaluation records can contain paper excerpts or local paths even when whole PDFs are excluded. Review them for permission and privacy before sharing. No project license file is currently present; repository availability does not grant an assumed open-source license.

## Archive a reproducible run separately

Preserve the permitted original PDFs, pinned model caches, indexes, lexical/reranker assets, actual prompts and responses, protocol, and manifests. Verify file hashes. A source snapshot alone does not reconstruct those assets, and a provider model alias does not guarantee future responses will match.

Git ignore rules and removal from the current file tree do not erase prior commits. See [repository policy](../reference/repository-policy.md) for the tracking boundary.

[Documentation home](../README.md)
