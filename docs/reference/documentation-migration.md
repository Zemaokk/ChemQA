# Documentation migration

Migration date: 2026-10-09.

Previous documentation is preserved locally at `legacy-docs/2026-10-09/`, using original repository-relative paths. Its `MANIFEST.json` records SHA-256 for every archived file. Original copies are not edited to repair historical links; the table below resolves retired paths to current documentation. The archive is Git-ignored and excluded from source snapshots.

All old prose in `docs/`, the old batch README, and `doc/report.pdf` were removed from the active tree. Root/data READMEs were rewritten. Machine JSON records remain at their original paths; frozen evaluation rubrics remain byte-identical because scripts and protocols hash them. Their historical path strings/hashes are provenance, not current navigation. No scientific scores or runtime manifests were rewritten.

| Previous path | Current entry point | Treatment |
| --- | --- | --- |
| `README.md` | [README.md](../../README.md) | Rewritten. |
| `data/README.md` | [data/README.md](../../data/README.md) | Rewritten. |
| `doc/report.pdf` | [docs/explanation/architecture.md](../../docs/explanation/architecture.md) | Archived; content consolidated. |
| `docs/DEMO.md` | [docs/how-to/inspect-evidence.md](../../docs/how-to/inspect-evidence.md) | Archived; content consolidated. |
| `docs/EVALUATION_GUIDE.md` | [docs/reference/evaluation.md](../../docs/reference/evaluation.md) | Archived; content consolidated. |
| `docs/P3_EXPERIMENT_PLAN.md` | [docs/reference/evaluation.md](../../docs/reference/evaluation.md) | Archived; content consolidated. |
| `docs/P3_EXPERIMENT_RESULTS.md` | [docs/explanation/evaluation-results.md](../../docs/explanation/evaluation-results.md) | Archived; content consolidated. |
| `docs/P3_QUESTION_REVIEW.md` | [docs/reference/evaluation.md](../../docs/reference/evaluation.md) | Archived; content consolidated. |
| `docs/P3_REVIEW_DISPUTES.md` | [docs/reference/evaluation.md](../../docs/reference/evaluation.md) | Archived; content consolidated. |
| `docs/P3_SEND_SCOPE.md` | [docs/reference/experiment-records.md](../../docs/reference/experiment-records.md) | Archived; content consolidated. |
| `docs/Q01_IDENTITY.md` | [docs/reference/artifact-contracts.md](../../docs/reference/artifact-contracts.md) | Archived; content consolidated. |
| `docs/Q02_LOCATIONS.md` | [docs/reference/artifact-contracts.md](../../docs/reference/artifact-contracts.md) | Archived; content consolidated. |
| `docs/Q03_TEXT_PROCESSING.md` | [docs/reference/retrieval.md](../../docs/reference/retrieval.md) | Archived; content consolidated. |
| `docs/Q04_SIMILARITY.md` | [docs/reference/retrieval.md](../../docs/reference/retrieval.md) | Archived; content consolidated. |
| `docs/Q05_PROMPT_CONTRACT.md` | [docs/reference/artifact-contracts.md](../../docs/reference/artifact-contracts.md) | Archived; content consolidated. |
| `docs/Q06_5A_REFERENCE.md` | [docs/reference/experiment-records.md](../../docs/reference/experiment-records.md) | Archived; content consolidated. |
| `docs/Q06_5B_ANSWER_REVIEW.md` | [docs/reference/evaluation.md](../../docs/reference/evaluation.md) | Archived; content consolidated. |
| `docs/Q06_5B_GENERATION.md` | [docs/reference/evaluation.md](../../docs/reference/evaluation.md) | Archived; content consolidated. |
| `docs/Q06_5B_SEND_SCOPE.md` | [docs/reference/experiment-records.md](../../docs/reference/experiment-records.md) | Archived; content consolidated. |
| `docs/Q06_5C_ENVIRONMENT.md` | [docs/reference/cli-and-configuration.md](../../docs/reference/cli-and-configuration.md) | Archived; content consolidated. |
| `docs/Q06_5D_PARSING.md` | [docs/decisions/0006-retain-pymupdf-extraction.md](../../docs/decisions/0006-retain-pymupdf-extraction.md) | Archived; content consolidated. |
| `docs/Q06_5E_EMBEDDING.md` | [docs/reference/retrieval.md](../../docs/reference/retrieval.md) | Archived; content consolidated. |
| `docs/Q06_5F_STORAGE.md` | [docs/decisions/0003-store-candidate-vectors-in-numpy-and-sqlite.md](../../docs/decisions/0003-store-candidate-vectors-in-numpy-and-sqlite.md) | Archived; content consolidated. |
| `docs/Q06_5G_HYBRID.md` | [docs/reference/retrieval.md](../../docs/reference/retrieval.md) | Archived; content consolidated. |
| `docs/Q06_5H_RERANKING.md` | [docs/reference/retrieval.md](../../docs/reference/retrieval.md) | Archived; content consolidated. |
| `docs/Q06_5I_CONTEXT.md` | [docs/reference/retrieval.md](../../docs/reference/retrieval.md) | Archived; content consolidated. |
| `docs/Q06_5J_FREEZE.md` | [docs/how-to/frozen-runtime.md](../../docs/how-to/frozen-runtime.md) | Archived; content consolidated. |
| `docs/Q06_5_MODERNIZATION_PLAN.md` | [docs/explanation/project-status.md](../../docs/explanation/project-status.md) | Archived; content consolidated. |
| `docs/Q06_EVIDENCE_BOUNDARIES.md` | [docs/explanation/answer-reliability.md](../../docs/explanation/answer-reliability.md) | Archived; content consolidated. |
| `docs/Q07_API_RESULTS.md` | [docs/reference/artifact-contracts.md](../../docs/reference/artifact-contracts.md) | Archived; content consolidated. |
| `docs/Q08_REPRODUCIBILITY.md` | [docs/reference/artifact-contracts.md](../../docs/reference/artifact-contracts.md) | Archived; content consolidated. |
| `docs/Q09_CREDENTIALS.md` | [docs/how-to/share-source.md](../../docs/how-to/share-source.md) | Archived; content consolidated. |
| `docs/Q0_ENVIRONMENT.md` | [docs/reference/cli-and-configuration.md](../../docs/reference/cli-and-configuration.md) | Archived; content consolidated. |
| `docs/Q10A_EVALUATION.md` | [docs/reference/evaluation.md](../../docs/reference/evaluation.md) | Archived; content consolidated. |
| `docs/Q10A_REVIEW.md` | [docs/reference/evaluation.md](../../docs/reference/evaluation.md) | Archived; content consolidated. |
| `docs/Q10B_EVALUATION.md` | [docs/reference/evaluation.md](../../docs/reference/evaluation.md) | Archived; content consolidated. |
| `docs/Q10B_EXPERT_REVIEW.md` | [docs/explanation/evaluation-results.md](../../docs/explanation/evaluation-results.md) | Archived; content consolidated. |
| `docs/Q10B_SEND_SCOPE.md` | [docs/reference/experiment-records.md](../../docs/reference/experiment-records.md) | Archived; content consolidated. |
| `docs/Q11_DOCUMENTATION.md` | [docs/explanation/project-status.md](../../docs/explanation/project-status.md) | Archived; content consolidated. |
| `docs/R01_ANSWER_RELIABILITY.md` | [docs/explanation/answer-reliability.md](../../docs/explanation/answer-reliability.md) | Archived; content consolidated. |
| `docs/REFACTOR_PLAN.md` | [docs/explanation/project-status.md](../../docs/explanation/project-status.md) | Archived; content consolidated. |
| `docs/REPOSITORY_POLICY.md` | [docs/reference/repository-policy.md](../../docs/reference/repository-policy.md) | Archived; content consolidated. |
| `docs/RUNBOOK.md` | [docs/how-to/README.md](../../docs/how-to/README.md) | Archived; content consolidated. |
| `docs/TECHNICAL_REPORT.md` | [docs/explanation/architecture.md](../../docs/explanation/architecture.md) | Archived; content consolidated. |
| `evaluation/RUBRIC.md` | [docs/reference/evaluation.md](../../docs/reference/evaluation.md) | Retained byte-for-byte as a frozen protocol input; current overview replaced. |
| `evaluation/p3/RUBRIC.md` | [docs/reference/evaluation.md](../../docs/reference/evaluation.md) | Retained byte-for-byte as a frozen protocol input; current overview replaced. |
| `evaluation/q10b/RUBRIC.md` | [docs/reference/evaluation.md](../../docs/reference/evaluation.md) | Retained byte-for-byte as a frozen protocol input; current overview replaced. |
| `qa_testing/README_qa_testing.md` | [docs/how-to/batch-and-heatmaps.md](../../docs/how-to/batch-and-heatmaps.md) | Archived; content consolidated. |

The [record catalog](experiment-records.md) is the current entry point for unchanged structured evidence. Exact archived prose is local-only; current source documentation does not link to it as a required resource.

[Documentation home](../README.md)
