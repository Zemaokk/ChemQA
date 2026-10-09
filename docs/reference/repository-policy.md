# Repository file policy

| Content | Policy |
| --- | --- |
| Source, scripts, tests, configuration, dependency locks | Track in Git. |
| Current Markdown documentation, ADRs, changelog | Track in Git. |
| Small experiment JSON records and frozen evaluation inputs/rubrics | Track; these are validation inputs and may contain excerpts/paths. |
| `.env` and other local configuration | Ignore, except the credential-free `.env.example`. |
| `data/raw_papers`, `data/processed`, `data/vector_db` | Local only; permitted separate backup. |
| `models/` | Local weights/caches; record IDs and revisions rather than uploading weights. |
| `output/`, historical generated-answer directories, logs | Local only; archive experiment artifacts separately. |
| `legacy-docs/` | Local-only previous documentation snapshot, including the old authored report. |
| `data/README.md` | Track the current data-directory guide. |

Ignore rules are directory-specific rather than blanket JSON/PDF/image exclusions. Reviewed assets may be legitimate source material. A custom output destination needs its own ignore rule.

The archive policy does not remove earlier Git commits. Old tracked prose is deleted from the current source tree; the archive itself is untracked and omitted from prepared source snapshots. It is not a backup of PDFs, models, or generated runs. Preserve those separately when required for reproduction.

The current repository has no project license file. Excluding full PDFs does not make excerpts or local paths automatically suitable for redistribution. Source sharing uses the [snapshot workflow](../how-to/share-source.md).

[Documentation migration](documentation-migration.md) · [Documentation home](../README.md)
