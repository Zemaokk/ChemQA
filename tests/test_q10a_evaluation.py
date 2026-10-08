import json
import shutil
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

from scripts.prepare_source_release import include_source
from scripts.validate_q10a import evaluate_rankings
from src.evaluation.dataset import DATASET_DIR, read_json, validate_dataset
from src.evaluation.metrics import (
    aggregate_metrics,
    covered_characters,
    manual_review_template,
    retrieval_metrics,
)
from src.utils.artifacts import sha256_file


def anchor(doc="a", eid="e1"):
    return {
        "doc_id": doc,
        "evidence_id": eid,
        "page_number": 1,
        "char_start": 10,
        "char_end": 30,
    }


def hit(start, end, *, doc="a", page=1, located=True):
    return {
        "document": {
            "doc_id": doc,
            "location_status": "located" if located else "unlocated",
            "source_spans": [
                {"page_number": page, "char_start": start, "char_end": end}
            ],
        },
        "score": 0.9,
    }


def question(anchors=None):
    anchors = anchors or [anchor()]
    return {
        "answerability": "answerable",
        "evidence": anchors,
        "answer_points": [{"evidence_ids": [a["evidence_id"] for a in anchors]}],
    }


def edit_dataset(directory, name, mutate):
    data = read_json(directory / name)
    mutate(data)
    (directory / name).write_text(
        json.dumps(data, ensure_ascii=False), encoding="utf-8"
    )
    manifest = read_json(directory / "manifest.json")
    manifest["files_sha256"][name] = sha256_file(directory / name)
    (directory / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")


class Q10AEvaluationTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.copied_dataset = Path(temp.name) / "evaluation"
        shutil.copytree(DATASET_DIR, self.copied_dataset)

    def test_interval_union_and_clipping(self):
        assert (
            covered_characters(anchor(), [hit(0, 20), hit(15, 25), hit(15, 25)]) == 15
        )
        assert covered_characters(anchor(), [hit(0, 20), hit(20, 40)]) == 20

    def test_wrong_source_or_unknown_location_has_no_coverage(self):
        for kwargs in [{"doc": "b"}, {"page": 2}, {"located": False}]:
            assert covered_characters(anchor(), [hit(0, 40, **kwargs)]) == 0

    def test_document_hit_is_not_complete_evidence(self):
        result = retrieval_metrics(question(), [hit(10, 20), hit(20, 30)], (1, 2))
        assert result["at_k"]["1"]["annotated_doc_hit"] == 1
        assert result["at_k"]["1"]["complete_anchor_recall"] == 0
        assert result["at_k"]["2"]["all_anchors_complete"] == 1
        assert result["rr_first_complete_anchor"] == 0.5
        assert (
            retrieval_metrics(question(), [hit(10, 19), hit(20, 30)])[
                "rr_first_complete_anchor"
            ]
            == 0
        )

    def test_comparison_requires_both_documents_and_anchors(self):
        q = question([anchor(), anchor("b", "e2")])
        result = retrieval_metrics(q, [hit(10, 30), hit(10, 30, doc="b")], (1, 2))
        assert result["at_k"]["1"]["annotated_doc_recall"] == 0.5
        assert result["at_k"]["1"]["annotated_point_evidence_complete"] == 0
        assert result["at_k"]["2"]["annotated_point_evidence_complete"] == 1

    def test_insufficient_cases_are_unscored_not_successful(self):
        q = question()
        q["answerability"] = "scoped_insufficient"
        assert retrieval_metrics(q, []) is None
        assert aggregate_metrics([{"m": None}], "m") == {
            "scored_questions": 0,
            "metrics": None,
        }
        valid = retrieval_metrics(question(), [])
        assert (
            aggregate_metrics([{"m": None}, {"m": valid}], "m")["scored_questions"] == 1
        )

    def test_manual_template_is_not_a_quality_measurement(self):
        rows = read_json(DATASET_DIR / "dev.json")["questions"]
        result = manual_review_template(rows)
        assert result["status"] == "not_scored"
        assert result["reviewer"] is None
        assert all(
            p["score"] is None for r in result["questions"] for p in r["point_scores"]
        )

    def test_frozen_checksum_rejects_unversioned_edit(self):
        copied_dataset = self.copied_dataset
        with (copied_dataset / "dev.json").open("a") as handle:
            handle.write(" ")
        with self.assertRaisesRegex(ValueError, "checksum"):
            validate_dataset(copied_dataset, verify_sources=False)

    def test_exact_pdf_interval_not_just_quote_length(self):
        copied_dataset = self.copied_dataset

        def corrupt(data):
            evidence = data["questions"][0]["evidence"][0]
            evidence["quote"] = "?" + evidence["quote"][1:]

        edit_dataset(copied_dataset, "dev.json", corrupt)
        with self.assertRaisesRegex(ValueError, "exact PDF interval"):
            validate_dataset(copied_dataset)

    def test_approval_requires_real_reviewer(self):
        copied_dataset = self.copied_dataset

        def approve(data):
            data["questions"][0]["annotation"]["review_status"] = "approved"

        edit_dataset(copied_dataset, "dev.json", approve)
        with self.assertRaisesRegex(ValueError, "human reviewer"):
            validate_dataset(copied_dataset, verify_sources=False)

    def test_article_split_rejects_overlap(self):
        copied_dataset = self.copied_dataset
        dev_anchor = read_json(DATASET_DIR / "dev.json")["questions"][0]["evidence"][0]

        def overlap(data):
            old_id = data["questions"][0]["evidence"][0]["evidence_id"]
            replacement = deepcopy(dev_anchor)
            replacement["evidence_id"] = old_id
            data["questions"][0]["evidence"][0] = replacement

        edit_dataset(copied_dataset, "reserve.json", overlap)
        with self.assertRaisesRegex(ValueError, "article groups overlap"):
            validate_dataset(copied_dataset, verify_sources=False)

    def test_answer_point_cannot_reference_missing_evidence(self):
        copied_dataset = self.copied_dataset

        def corrupt(data):
            data["questions"][0]["answer_points"][0]["evidence_ids"] = ["missing"]

        edit_dataset(copied_dataset, "dev.json", corrupt)
        with self.assertRaisesRegex(ValueError, "missing evidence"):
            validate_dataset(copied_dataset, verify_sources=False)

    def test_frozen_dataset_counts_and_domain_review_state(self):
        _, _, _, report = validate_dataset(verify_sources=False)
        assert report["split_counts"] == {"dev": 20, "reserve": 6}
        assert report["exact_evidence_intervals"] == 36
        assert report["domain_review_states"] == {"pending": 26}
        assert report["article_group_overlap"] == 0

    def test_reserve_execution_and_length_mismatch_rejected(self):
        reserve = read_json(DATASET_DIR / "reserve.json")["questions"][0]
        with self.assertRaisesRegex(ValueError, "Reserve evaluation"):
            evaluate_rankings([reserve], [[]])
        with self.assertRaises(ValueError):
            evaluate_rankings([read_json(DATASET_DIR / "dev.json")["questions"][0]], [])

    def test_empty_rankings_prepare_prompts_without_api_calls(self):
        import requests

        def forbidden(*args, **kwargs):
            raise AssertionError("Evaluation preparation must not call provider")

        self.enterContext(patch.object(requests.sessions.Session, "request", forbidden))
        rows = read_json(DATASET_DIR / "dev.json")["questions"]
        results = evaluate_rankings(rows, [[] for _ in rows])
        assert len(results) == 20
        assert all(
            r["empty_context"] and r["generation_status"] == "not_run" for r in results
        )
        assert all(r["generation_input"]["prompt_sent"] is False for r in results)
        assert all(r["quality_scores"] is None for r in results)

    def test_evaluation_files_included_in_future_source_exports(self):
        assert include_source("evaluation/dev.json")
        assert include_source("evaluation/RUBRIC.md")
        assert not include_source("evaluation/paper.pdf")

    def test_threshold_reports_raw_hits_separately_from_context(self):
        row = read_json(DATASET_DIR / "dev.json")["questions"][0]
        a = row["evidence"][0]
        ranked = hit(
            a["char_start"], a["char_end"], doc=a["doc_id"], page=a["page_number"]
        )
        ranked["score"] = 0.4
        result = evaluate_rankings([row], [[ranked]])[0]
        assert result["raw_metrics"]["at_k"]["1"]["all_anchors_complete"] == 1
        assert result["context_metrics"]["at_k"]["1"]["all_anchors_complete"] == 0
        assert result["empty_context"]
