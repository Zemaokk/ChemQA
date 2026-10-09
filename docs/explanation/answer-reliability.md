# Answer reliability and failure boundaries

Traceability is useful because scientific errors can survive a successful retrieval and a perfectly valid citation marker. A passage can be the right source yet omit the condition that makes a number meaningful. PDF extraction can lose a negative sign before a model ever sees the evidence.

The current conservative R01 prompt asks the model to answer only the requested metrics, bind values to the relevant experiment, preserve uncertainty, avoid reconstructing damaged charged equations, and limit statements about absent evidence to the retrieved scope.

The guarded generator adds lexical checks for some number/unit and citation mismatches, expanded equations, anomalous percentages, and overly broad absence claims. A rejection preserves the response and findings as a failure, without publishing an ordinary answer or automatically retrying. Direct use of historical generator classes and the independent direct-API utility bypasses these current answer checks.

These checks do not prove semantic condition binding, charge conservation, or source fidelity. A number appearing in the cited paragraph may belong to another experiment. Conversely, valid unit formatting, adjacent Chinese text, or different metric spelling can trigger a rule. `passed_lexical_checks` leaves scientific support unverified.

P3 makes this tradeoff visible: 78 of 90 RAG generations were rejected. Raw required-point coverage was high, while delivered-score improvement was uncertain. Some rejections reflect answer over-expansion; at least one documented case rejected a concise correct requested metric. Calling all rejections scientific errors or all of them false positives would misstate the evidence.

The next revision needs both narrower generation and better recognition of requested metrics, tested on new questions. Improving acceptance alone would not establish scientific quality; strengthening rejection alone would not establish useful delivery.

[Evaluation results](evaluation-results.md) · [Inspect a rejected answer](../how-to/inspect-evidence.md) · [Decision record](../decisions/0005-isolate-rejected-answers.md) · [Documentation home](../README.md)
