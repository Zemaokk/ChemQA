# What the evaluations establish

The studies below measure different stages and configurations. They should not be combined into one accuracy number. Scoring is exploratory, with no independent blind validation; disputed cases remain open. This page summarizes existing records without re-running generation.

## Development retrieval and storage

| Comparison | Recorded observation | Scope |
| --- | --- | --- |
| Legacy vs Qwen chunking/embedding | Complete-anchor recall@10: 5.6% vs 62.0% | Joint model/window change on 18 development positives; different text budgets. |
| JSON vs NumPy/SQLite | 221.6 → 61.3 MiB; identical vectors, metadata, and top-ten rankings | Same 6,960 rows; storage improvement, not retrieval-quality improvement. |
| Dense vs hybrid retrieval | 62.0% → 70.37% complete-anchor recall@10 | Development labels, not exhaustive relevance judgments. |
| Hybrid vs fixed-pool reranking | 70.37% → 85.19%; median added reranking time 7.62 s | Same 50 candidates, local development evaluation. |
| Diversity selection | 85.19% → 82.41% | Per-paper cap caused a regression; retained as an experiment. |

The storage benchmark observed loading medians of 2.07 vs 0.37 s and search medians of 8.11 vs 1.12 ms. It excluded model loading/query encoding; filesystem caches were not controlled. It is not an end-to-end performance claim. See [benchmark](../Q06_5F_BENCHMARK.json), [embedding](../Q06_5E_FULL.json), [hybrid](../Q06_5G_FULL.json), [reranking](../Q06_5H_FULL.json), and [selection](../Q06_5I_FULL.json) records.

## Q10-B: six reserved questions

Five configurations generated three repetitions per question, giving 90 completed responses. Frozen required-point macro-averages were 15.28% for direct, 77.78% for BM25, and 100% for each of Qwen dense, hybrid/reranking, and diversity selection.

Required-point credit did not account for every additional claim. Recorded answers still mixed experimental stages, reconstructed damaged equations incorrectly, or overstated absent controls. The study did not compare legacy MiniLM generation under the same conditions. Six questions and a non-blind exploratory review do not establish a general winner or justify switching the default. See [scored results](../Q10B_EXPERT_RESULTS.json) and [per-answer records](../Q10B_EXPERT_ANSWERS.json).

## P3: new questions and delivered answers

P3 used 30 questions from 20 article groups, direct generation versus frozen R01 hybrid/reranking, with three repetitions: 180 responses. All requests returned complete responses without extra attempts.

| Article-group macro-average | Direct | R01 RAG | Paired difference |
| --- | ---: | ---: | --- |
| Strict necessary-point score | 3.33% | 96.67% | +93.33 percentage points; 95% interval [86.67, 98.75] |
| Major-error-penalized score | 3.33% | 96.67% | Same |
| Delivered score, rejected answers counted zero | 3.33% | 9.17% | +5.83 percentage points; 95% interval [−4.17, 16.25] |

Publication checks rejected 78/90 RAG answers. Five direct answers and zero RAG answers had identified major errors in the initial classification; this is not an exhaustive scientific error rate. The delivered-score interval includes zero, so the evidence does not establish a stable improvement in actual delivery.

The checked RAG fact units numbered 651: 610 cited and 601 fully supported. Within those checked units, support was 98.52% and citation coverage 93.70%. Units were not an exhaustive atomic decomposition of every answer; some combine related facts. Those rates do not establish whole-answer support or zero hallucinations.

P3 questions were new to the prior labeled/generated question sources, but their papers were already indexed. They focus on abstract/first-page facts. Direct and RAG used different evidence-specific prompts, so the comparison measures complete configurations rather than a pure retrieval-algorithm effect. Provider training data and underlying model revision are unknown.

The paired interval resamples 20 article groups, not 180 independent answers, and excludes scoring/selection bias and future model drift. API medians were 2.59 s direct and 5.36 s RAG; these exclude retrieval. Provider-reported usage was 34,044 and 678,622 total tokens respectively; monetary cost is unknown.

Open adjudications include inconsistent acceptance of general knowledge in direct answers, compound required points, omitted MD/HER details, source-condition discrepancies, molecule-name expansion, citation support mismatches, and requested-metric rejection. Later adjudications must be versioned separately. See [results](../P3_RESULTS.json), [scored records](../P3_ASSISTANT_REVIEW.json), and [execution validation](../P3_EXECUTION_VALIDATION.json).

[Metric definitions](../reference/evaluation.md) · [Current status](project-status.md) · [Documentation home](../README.md)
