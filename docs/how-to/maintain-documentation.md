# Maintain documentation, ADRs, and the changelog

## Choose the document's purpose

Use [Diátaxis](https://diataxis.fr/start-here/) to select one purpose before writing:

| Reader's need | Location | Content |
| --- | --- | --- |
| Learn by completing an exercise | `docs/tutorials/` | A guided sequence with prerequisites and observable outcomes. |
| Accomplish a specific task | `docs/how-to/` | Focused steps and necessary choices. |
| Look up an interface | `docs/reference/` | Flags, defaults, fields, schemas, and metric definitions. |
| Understand a design or result | `docs/explanation/` | Reasoning, evidence, tradeoffs, and limitations. |

Link to the other forms when needed rather than expanding one page into all four. Use English for current prose, descriptive lowercase hyphenated filenames, relative repository links, and one clear subject per page. Keep the README an entry point. Do not add contributor-identity commentary to product documentation.

## Record a significant decision

Copy the [ADR template](../decisions/template.md) to the next numbered filename. Use Proposed until accepted, then record the date, one decision, context, alternatives, and consequences. Link to owning source and records. Existing choices documented after the fact must say they are retrospective.

Add the record to the [decision index](../decisions/README.md). When replacing a decision, create a new accepted ADR, link both records, and mark the previous one Superseded with a dated note. Preserve its original rationale.

## Record a notable change

Add a concise user-facing entry to root [CHANGELOG.md](../../CHANGELOG.md) under `Unreleased`, using relevant categories from [Keep a Changelog](https://keepachangelog.com/en/1.1.0/): Added, Changed, Deprecated, Removed, Fixed, Security. Do not paste commit logs.

At an actual release, move the accumulated changes into a version section dated `YYYY-MM-DD`, newest first. Add real release/compare links only when those tags exist. `pyproject.toml` has package version 0.1.0, but this migration does not invent a release date, release tag, or established Semantic Versioning policy.

## Update links and preserve records

Update the documentation home, affected section indexes, README, and any code/configuration comments pointing to a moved guide. Use [the migration map](../reference/documentation-migration.md) for historical paths. Frozen machine records can legitimately name historical documents; their stored paths/hashes describe the earlier snapshot and must not be rewritten as current links.

Do not edit frozen rubric or protocol files to refresh prose. Create a new version if their rules change. Historical scripts that generate scope documents write local output, not new top-level user guides. The ignored archive must stay outside source-release allowlists.

## Verify before delivery

Run the documentation checker from the project root:

```sh
uv run --locked python -m scripts.check_documentation
```

It checks current Markdown links and anchors, obsolete prose references in code/configuration, archive integrity, and archive exclusion from source snapshots. It does not request external URLs or validate scientific claims.

If a release utility changes, run its relevant regression tests. If runtime-bound files change, validate all three current profiles and create a new runtime version when required. Documentation-only changes should leave experimental hashes intact.

[Documentation home](../README.md)
