# Experiment record catalog

These JSON files are frozen machine-readable evidence or script inputs, not current user guides. Their names and bytes are retained to preserve script paths and manifest hashes. Historical embedded paths refer to their original snapshot; use the [migration map](documentation-migration.md) for retired prose. Original PDF/model/run directories remain separately archived local assets.

| Study | Start with | Meaning |
| --- | --- | --- |
| Q01–Q08 | Stage validation JSON below | Identity, source locations, input length, cosine, prompt, boundaries, API state, and isolated runs. |
| Q06.5 A–C | Baseline/generation/environment records | Historical reference, provider baseline, and locked environment. |
| Q06.5 D–I | FULL, REPLAY, RUNTIME, and VALIDATION records | Parser trial, embedding/chunking, storage, hybrid, reranking, and context selection. |
| Q06.5 J | CLOSEOUT and VALIDATION | Original runtime freeze; current CLI uses the R01 manifest. |
| Q09 | SECRET_AUDIT and VALIDATION | Credential-pattern scope and source-sharing checks. |
| Q10-A/B | Protocol, preview, generation, results, and separate scored layers | Initial evaluation and consumed reserved-set comparison. |
| R01 | VALIDATION | Conservative answer-policy engineering revision. |
| P3 | RESULTS, ASSISTANT_REVIEW, and EXECUTION_VALIDATION | New article-specific comparison, checked facts, and guard outcomes. |

P3 initial scoring has unresolved acceptance-scope and source-attribution disputes. Preserve the original review and add later adjudications separately. `SEND_APPROVAL` and consumed markers describe historical request scopes; they are not authorization for new external requests.

The staged results are explained in [evaluation results](../explanation/evaluation-results.md). Full field meanings are in [evaluation reference](evaluation.md). Historical stage scripts may write fixed JSON reports; do not overwrite bound records as part of ordinary reading.

## Record files

### P3

- [P3_ASSISTANT_REVIEW.json](../P3_ASSISTANT_REVIEW.json)
- [P3_EXECUTION_VALIDATION.json](../P3_EXECUTION_VALIDATION.json)
- [P3_INPUT_SOURCE_INTEGRITY.json](../P3_INPUT_SOURCE_INTEGRITY.json)
- [P3_PREPARATION_VALIDATION.json](../P3_PREPARATION_VALIDATION.json)
- [P3_PREVIEW_RESTART.json](../P3_PREVIEW_RESTART.json)
- [P3_RESULTS.json](../P3_RESULTS.json)
- [P3_SELECTED_EVIDENCE.json](../P3_SELECTED_EVIDENCE.json)
- [P3_SEND_APPROVAL.json](../P3_SEND_APPROVAL.json)
- [P3_SOURCE_CHECK.json](../P3_SOURCE_CHECK.json)

### Q01

- [Q01_VALIDATION.json](../Q01_VALIDATION.json)

### Q02

- [Q02_VALIDATION.json](../Q02_VALIDATION.json)

### Q03

- [Q03_VALIDATION.json](../Q03_VALIDATION.json)

### Q04

- [Q04_VALIDATION.json](../Q04_VALIDATION.json)

### Q05

- [Q05_VALIDATION.json](../Q05_VALIDATION.json)

### Q06

- [Q06_VALIDATION.json](../Q06_VALIDATION.json)

### Q06_5A

- [Q06_5A_BASELINE.json](../Q06_5A_BASELINE.json)
- [Q06_5A_REPLAY.json](../Q06_5A_REPLAY.json)
- [Q06_5A_RESTORED_REPLAY.json](../Q06_5A_RESTORED_REPLAY.json)

### Q06_5B

- [Q06_5B_BASELINE.json](../Q06_5B_BASELINE.json)
- [Q06_5B_PREFLIGHT.json](../Q06_5B_PREFLIGHT.json)
- [Q06_5B_PREVIEW.json](../Q06_5B_PREVIEW.json)
- [Q06_5B_SMOKE.json](../Q06_5B_SMOKE.json)
- [Q06_5B_VALIDATION.json](../Q06_5B_VALIDATION.json)

### Q06_5C

- [Q06_5C_LEGACY.json](../Q06_5C_LEGACY.json)
- [Q06_5C_RUNTIME.json](../Q06_5C_RUNTIME.json)
- [Q06_5C_VALIDATION.json](../Q06_5C_VALIDATION.json)

### Q06_5D

- [Q06_5D_REVIEW.json](../Q06_5D_REVIEW.json)
- [Q06_5D_RUNTIME.json](../Q06_5D_RUNTIME.json)
- [Q06_5D_SAMPLE.json](../Q06_5D_SAMPLE.json)
- [Q06_5D_SECRET_AUDIT.json](../Q06_5D_SECRET_AUDIT.json)
- [Q06_5D_VALIDATION.json](../Q06_5D_VALIDATION.json)

### Q06_5E

- [Q06_5E_CORPUS.json](../Q06_5E_CORPUS.json)
- [Q06_5E_FULL.json](../Q06_5E_FULL.json)
- [Q06_5E_FULL_FAILURES.json](../Q06_5E_FULL_FAILURES.json)
- [Q06_5E_LEGACY_REPLAY.json](../Q06_5E_LEGACY_REPLAY.json)
- [Q06_5E_PILOT.json](../Q06_5E_PILOT.json)
- [Q06_5E_PILOT_FAILURES.json](../Q06_5E_PILOT_FAILURES.json)
- [Q06_5E_REPLAY.json](../Q06_5E_REPLAY.json)
- [Q06_5E_RESOURCE.json](../Q06_5E_RESOURCE.json)
- [Q06_5E_RUN_NOTES.json](../Q06_5E_RUN_NOTES.json)
- [Q06_5E_SECRET_AUDIT.json](../Q06_5E_SECRET_AUDIT.json)
- [Q06_5E_VALIDATION.json](../Q06_5E_VALIDATION.json)

### Q06_5F

- [Q06_5F_BENCHMARK.json](../Q06_5F_BENCHMARK.json)
- [Q06_5F_FAISS_TRIAL.json](../Q06_5F_FAISS_TRIAL.json)
- [Q06_5F_FULL.json](../Q06_5F_FULL.json)
- [Q06_5F_REPLAY.json](../Q06_5F_REPLAY.json)
- [Q06_5F_RUNTIME.json](../Q06_5F_RUNTIME.json)
- [Q06_5F_SECRET_AUDIT.json](../Q06_5F_SECRET_AUDIT.json)
- [Q06_5F_VALIDATION.json](../Q06_5F_VALIDATION.json)

### Q06_5G

- [Q06_5G_FAILURES.json](../Q06_5G_FAILURES.json)
- [Q06_5G_FULL.json](../Q06_5G_FULL.json)
- [Q06_5G_REPLAY.json](../Q06_5G_REPLAY.json)
- [Q06_5G_RUNTIME.json](../Q06_5G_RUNTIME.json)
- [Q06_5G_SECRET_AUDIT.json](../Q06_5G_SECRET_AUDIT.json)
- [Q06_5G_VALIDATION.json](../Q06_5G_VALIDATION.json)

### Q06_5H

- [Q06_5H_FAILURES.json](../Q06_5H_FAILURES.json)
- [Q06_5H_FULL.json](../Q06_5H_FULL.json)
- [Q06_5H_REPLAY.json](../Q06_5H_REPLAY.json)
- [Q06_5H_RUNTIME.json](../Q06_5H_RUNTIME.json)
- [Q06_5H_SECRET_AUDIT.json](../Q06_5H_SECRET_AUDIT.json)
- [Q06_5H_VALIDATION.json](../Q06_5H_VALIDATION.json)

### Q06_5I

- [Q06_5I_FAILURES.json](../Q06_5I_FAILURES.json)
- [Q06_5I_FULL.json](../Q06_5I_FULL.json)
- [Q06_5I_REPLAY.json](../Q06_5I_REPLAY.json)
- [Q06_5I_SECRET_AUDIT.json](../Q06_5I_SECRET_AUDIT.json)
- [Q06_5I_VALIDATION.json](../Q06_5I_VALIDATION.json)

### Q06_5J

- [Q06_5J_CLOSEOUT.json](../Q06_5J_CLOSEOUT.json)
- [Q06_5J_VALIDATION.json](../Q06_5J_VALIDATION.json)

### Q07

- [Q07_VALIDATION.json](../Q07_VALIDATION.json)

### Q08

- [Q08_VALIDATION.json](../Q08_VALIDATION.json)

### Q09

- [Q09_SECRET_AUDIT.json](../Q09_SECRET_AUDIT.json)
- [Q09_VALIDATION.json](../Q09_VALIDATION.json)

### Q10A

- [Q10A_BASELINE.json](../Q10A_BASELINE.json)
- [Q10A_REPLAY.json](../Q10A_REPLAY.json)
- [Q10A_VALIDATION.json](../Q10A_VALIDATION.json)

### Q10B

- [Q10B_ANNOTATION_REVIEW.json](../Q10B_ANNOTATION_REVIEW.json)
- [Q10B_BASELINE_CITATIONS.json](../Q10B_BASELINE_CITATIONS.json)
- [Q10B_EXPERT_ANNOTATIONS.json](../Q10B_EXPERT_ANNOTATIONS.json)
- [Q10B_EXPERT_ANSWERS.json](../Q10B_EXPERT_ANSWERS.json)
- [Q10B_EXPERT_RESULTS.json](../Q10B_EXPERT_RESULTS.json)
- [Q10B_EXPERT_VALIDATION.json](../Q10B_EXPERT_VALIDATION.json)
- [Q10B_GENERATION.json](../Q10B_GENERATION.json)
- [Q10B_PREVIEW.json](../Q10B_PREVIEW.json)
- [Q10B_REPLAY.json](../Q10B_REPLAY.json)
- [Q10B_RESULTS.json](../Q10B_RESULTS.json)
- [Q10B_SECRET_AUDIT.json](../Q10B_SECRET_AUDIT.json)
- [Q10B_VALIDATION.json](../Q10B_VALIDATION.json)

### Q11

- [Q11_VALIDATION.json](../Q11_VALIDATION.json)

### R01

- [R01_VALIDATION.json](../R01_VALIDATION.json)

### Repository

- [GIT_HYGIENE_VALIDATION.json](../GIT_HYGIENE_VALIDATION.json)

[Documentation home](../README.md)
