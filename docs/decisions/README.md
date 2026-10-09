# Architecture decision records

Each record captures one consequential decision with status, context, decision, alternatives, and consequences. Existing implementation choices below are documented retrospectively on 2026-10-09; this date does not imply they were first made then.

| ADR | Status | Decision |
| --- | --- | --- |
| [0001](0001-organize-documentation-by-user-need.md) | Accepted | Organize current documentation by user need. |
| [0002](0002-identify-evidence-by-content.md) | Accepted; retrospective | Use content identities and extracted-text source spans. |
| [0003](0003-store-candidate-vectors-in-numpy-and-sqlite.md) | Accepted; retrospective | Use NumPy/SQLite for experimental binary indexes. |
| [0004](0004-retain-compatible-default.md) | Accepted; retrospective | Retain MiniLM/JSON as the compatibility default. |
| [0005](0005-isolate-rejected-answers.md) | Accepted; retrospective | Preserve rejected answers as diagnostic failures. |
| [0006](0006-retain-pymupdf-extraction.md) | Accepted; retrospective | Retain PyMuPDF as the source extractor. |

Use the [template](template.md) for proposals. A new accepted decision that replaces an earlier choice links to the earlier ADR and marks it superseded; do not silently rewrite its historical rationale. Routine bug fixes belong in the changelog and tests rather than an ADR.

Format follows the context/decision/consequences approach described by [Architecture Decision Records](https://github.com/architecture-decision-record/architecture-decision-record). See [documentation maintenance](../how-to/maintain-documentation.md) for the lifecycle.

[Documentation home](../README.md)
