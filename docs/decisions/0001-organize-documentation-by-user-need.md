# 0001. Organize documentation by user need

Date: 2026-10-09  
Status: Accepted

## Context

The former documentation mixed installation instructions, current interfaces, plans, and chronological experiment reports. Many documents reflected intermediate states. Machine-readable records and frozen rubrics are also executable validation inputs, so moving every file would break runtime checks.

## Decision

Use Diátaxis directories for tutorials, how-to guides, reference, and explanation. Keep ADRs in `docs/decisions/` and curated user-facing changes in root `CHANGELOG.md`. Archive previous prose and the authored PDF under ignored `legacy-docs/2026-10-09/`. Preserve machine records and frozen rubric bytes at their existing paths. Replace active links rather than maintaining duplicate old guides.

## Alternatives

Renaming the old documents into four folders would preserve their mixed purposes and stale status. Moving all JSON records would require a runtime/protocol migration unrelated to the documentation task. Leaving old prose beside new guides would create competing authorities.

## Consequences

Current docs are easier to navigate and maintain by intent. Historical prose is local-only; source checkouts retain machine evidence but not that archive. Future new runs must not recreate obsolete guides as current documentation. The migration map and archive hashes make the change inspectable. Runtime manifests and scientific results remain unchanged.

Evidence: [Migration map](../reference/documentation-migration.md) and [file policy](../reference/repository-policy.md).

[Decision index](README.md)
