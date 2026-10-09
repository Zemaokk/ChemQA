# Evaluation protocols and metrics

## Protocol versions

| Study | Scope | Current interpretation |
| --- | --- | --- |
| Q10-A | 20 development + 6 reserved questions | Historical source/metric preparation. |
| Q06.5-B | 20 development questions, one generation each | Historical generation/interface baseline. |
| E/G/H/I | 20 development queries, 18 positive queries in anchor macro-averages | Candidate selection, not independent testing. |
| Q10-B | 34 development + original 6 reserved questions; 5 arms × 3 repetitions on the reserved set | 90 completed generations; reserved questions consumed. |
| P3 | 30 new questions from 20 article groups, 2 configurations × 3 repetitions | 180 completed generations; exploratory scoring and unresolved adjudications. |

Frozen inputs remain in [evaluation](../../evaluation/) and the protocol configurations [Q10-B](../../config/q10b_protocol.json) and [P3](../../config/p3_experiment.json). Their `RUBRIC.md` files are immutable protocol inputs; current guides do not replace their hashes or retroactively change their rules.

## Retrieval metrics

Source matching uses PDF identity, physical page, and unioned character intervals. Repeated overlap is counted once.

| Metric | Definition |
| --- | --- |
| Annotated document hit | At least one labeled document in the first k results. |
| Annotated document recall | Distinct labeled documents retrieved / labeled documents for that question. |
| All annotated documents hit | All labeled documents retrieved. |
| Mean anchor character coverage | Covered fraction of each labeled interval, then average across anchors. |
| Complete anchor recall | Fully covered anchors / labeled anchors. |
| All anchors complete | All labeled intervals covered. |
| Annotated point evidence complete | Points whose required anchors are complete / labeled points. |
| Reciprocal first document/anchor rank | Reciprocal earliest matching document or cumulatively complete anchor rank; zero when absent in the evaluated window. |

Labels are not exhaustive. Unlabeled passages are unjudged, not automatically irrelevant. These metrics are not answer accuracy or recall over all scientifically relevant evidence.

## Generation scores

Q10-B assigns 0/1/2 per frozen point and normalizes by twice the point count. It averages repetitions per question, then the six questions. Conditions/units, system boundaries, evidence support, and citation correspondence are separate dimensions; not-applicable values remain null. Extra errors remain visible even when required points receive full credit.

P3 scores two necessary points per question as 0/1. At least one identified major extra error caps the answer score at 0.5. Publication rejection counts as zero for the delivered-score analysis. Scores are averaged across repetitions, then questions within an article, then equally across 20 article groups. Paired article bootstrap uses 10,000 samples and seed 20261008. Repeated generations are not independent article samples.

P3 cited-fact support measures only checked fact units: fully supported cited units / all cited checked units. Coverage is cited checked units / all checked units. Some units combine related facts and the audit is not exhaustive. These measures cannot be relabeled whole-answer atomic support or compared directly with Q10-B marker mapping.

## Structural and operational metrics

`marker_resolution_rate` is resolved citation markers / captured markers. Context chunk/document utilization counts cited input entries. A zero denominator is null, not 100%. These are structural measures, not scientific support scores.

`success`, `no_evidence`, `failed`, and `truncated` remain separate. An unstated historical status is unverified. Local no-evidence responses do not count as successful model generation. API latency excludes local retrieval; usage is provider-reported and unknown pricing leaves monetary cost null.

[Results and limitations](../explanation/evaluation-results.md) · [Evaluation operations](../how-to/evaluate.md) · [Documentation home](../README.md)
