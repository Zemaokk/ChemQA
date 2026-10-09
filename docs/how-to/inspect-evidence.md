# Check evidence for an answer

1. Open the run's `run.json`. Confirm its status and the question. Use `failure.json` for failed or truncated generations; an older answer from another run is not the result of this request.
2. Read `answer.evidence.json`, especially `generation_input`, the actual prompt, normalized evidence, and `generation_result`. Confirm `prompt_sent` and the selected runtime provenance where present.
3. Resolve the answer's displayed reference through its evidence map to the full `chunk_id` and `doc_id`. Display numbers are local to the answer.
4. Open the matching original PDF by byte identity. Go to the physical PDF page, then compare the saved `source_spans` with text extracted by the recorded extractor.
5. Inspect the rendered page for minus signs, charges, equations, superscripts, and table/figure attribution. Exact extracted-text matching does not guarantee faithful extraction.
6. Check that the cited passage supports the claim under the stated conditions. Separate measurement from interpretation, and keep different optimization stages distinct.

For an example of what to verify, the historical Q10-B R06 answer reports current density 100 mA cm⁻², LA productivity 268.1 μmol cm⁻² h⁻¹, and FE 28.7% for Au-catalyzed ethylene-glycol/methanol coupling. Its source anchors are in [the frozen question set](../../evaluation/q10b/reserve.json). These are different metrics; the final temperature must be checked in the paper's optimization discussion rather than inferred from another excerpt. This example is a provenance exercise, not a claim that the entire historical answer was correct.

For a rejected R01 answer, inspect `generation_input.answer_validation.findings` and `generation_result.partial_content` in `failure.json`. A rule finding identifies a detectable pattern, not a scientific verdict. A passed check also leaves `scientific_support_verified` false.

[Artifact fields](../reference/artifact-contracts.md) · [Documentation home](../README.md)
