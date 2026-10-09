"""Fresh-source, immutable-input and article-cluster scoring contracts for P3."""

import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import run_p3_experiment as p3
from src.utils.artifacts import sha256_file, write_json


class P3Tests(unittest.TestCase):
    def test_exact_sources_are_disjoint_with_twenty_groups_not_thirty(self):
        questions, documents = p3.validate_sources()
        self.assertEqual(len(questions), 30)
        self.assertEqual(len(documents), 20)
        self.assertEqual(len({q["article_group"] for q in questions}), 20)
        excluded = set(p3.read(p3.DATA / "exclusions.json")["excluded_doc_ids"])
        self.assertFalse(excluded & {d["doc_id"] for d in documents.values()})

    def test_changed_source_anchor_is_rejected(self):
        original = p3.read

        def changed(path):
            value = original(path)
            if Path(path).name == "questions.json":
                value = copy.deepcopy(value)
                value["questions"][0]["evidence"][0]["char_start"] += 1
            return value

        with (
            patch.object(p3, "read", side_effect=changed),
            self.assertRaisesRegex(ValueError, "source anchor"),
        ):
            p3.validate_sources()

    def test_approval_hash_mismatch_never_constructs_handler(self):
        with tempfile.TemporaryDirectory() as folder:
            directory = Path(folder)
            write_json(directory / "run.json", {})
            with (
                patch.object(p3, "verify_preview", return_value=[]),
                patch.object(p3, "DeepSeekAPIHandler") as handler,
                self.assertRaisesRegex(ValueError, "Approval"),
            ):
                p3.execute(directory, "wrong-preview")
            handler.assert_not_called()

    def test_bootstrap_uses_paired_article_groups_and_reports_percentage_points(self):
        result = p3.paired_bootstrap([0.25] * 20, samples=200)
        self.assertEqual(result["difference_pp"], 25)
        self.assertEqual(result["ci95_pp"], [25, 25])
        self.assertEqual(result["article_groups"], 20)

    def test_bootstrap_seed_is_reproducible_and_invalid_data_rejected(self):
        self.assertEqual(
            p3.paired_bootstrap([0, 0.3, -0.2]), p3.paired_bootstrap([0, 0.3, -0.2])
        )
        for values in [[], [float("nan")]]:
            with self.assertRaises(ValueError):
                p3.paired_bootstrap(values)

    def fixture(self, root):
        data, generation, review_dir = (
            root / "evaluation/p3",
            root / "generation",
            root / "review",
        )
        for folder in [data, generation, review_dir, root / "docs"]:
            folder.mkdir(parents=True)
        questions, reviews, mapping, files = [], [], {}, {}
        for i in range(30):
            qid, group = f"P3-{i + 1:02d}", f"group-{i % 20}"
            questions.append(
                {
                    "question_id": qid,
                    "article_group": group,
                    "answer_points": [{"point_id": "p1"}, {"point_id": "p2"}],
                }
            )
            for arm in p3.ARMS:
                for repetition in range(1, 4):
                    name = f"{qid}-{arm}-r{repetition}.json"
                    row = {
                        "question_id": qid,
                        "arm": arm,
                        "repetition": repetition,
                        "answer": "Synthetic answer",
                        "result": {"status": "success"},
                        "answer_validation": {
                            "status": "blocked"
                            if arm == "rag_r01"
                            else "passed_lexical_checks"
                        },
                    }
                    write_json(generation / name, row)
                    files[name] = sha256_file(generation / name)
                    rid = f"B{len(reviews) + 1:03d}"
                    mapping[rid] = {"filename": name, "sha256": files[name]}
                    reviews.append(
                        {
                            "review_id": rid,
                            "question_id": qid,
                            "answer": row["answer"],
                            "reviewer_id": "synthetic-reviewer",
                            "reviewer_kind": "ai_assistant",
                            "point_correct": {"p1": 1, "p2": int(arm == "rag_r01")},
                            "point_reasons": {
                                "p1": "source check",
                                "p2": "source check",
                            },
                            "major_errors": [],
                            "claims": [
                                {
                                    "text": "claim",
                                    "citation_markers": ["[Ref synthetic]"]
                                    if arm == "rag_r01"
                                    else [],
                                    "support_label": "supported"
                                    if arm == "rag_r01"
                                    else "uncited",
                                    "reason": "synthetic support check",
                                    "source_refs": [],
                                }
                            ],
                        }
                    )
        protocol = root / "protocol.json"
        write_json(protocol, {})
        write_json(data / "questions.json", {"questions": questions})
        write_json(
            generation / "run.json",
            {
                "status": "complete",
                "protocol_sha256": sha256_file(protocol),
                "files": files,
            },
        )
        write_json(review_dir / "mapping.json", mapping)
        write_json(review_dir / "review.json", reviews)
        write_json(
            review_dir / "run.json",
            {
                "generation_directory": "generation",
                "generation_run_sha256": sha256_file(generation / "run.json"),
            },
        )
        return data, generation, review_dir, protocol

    def run_fixture(self, root, fixture):
        data, _, review, protocol = fixture
        with (
            patch.object(p3, "ROOT", root),
            patch.object(p3, "DATA", data),
            patch.object(p3, "PROTOCOL", protocol),
            patch.object(p3, "check_protocol", return_value={}),
        ):
            p3.report(review)
        return p3.read(root / "docs/P3_RESULTS.json")

    def test_raw_blocked_answers_are_scored_but_delivery_is_zero(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            result = self.run_fixture(root, self.fixture(root))
            self.assertEqual(result["arms"]["rag_r01"]["strict_point_score"], 1)
            self.assertEqual(result["arms"]["rag_r01"]["delivered_score"], 0)
            self.assertEqual(
                result["paired_article_bootstrap"]["strict_point_score"][
                    "difference_pp"
                ],
                50,
            )
            self.assertEqual(result["article_groups"], 20)

    def test_major_error_caps_otherwise_perfect_core_score(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            fixture = self.fixture(root)
            reviews = p3.read(fixture[2] / "review.json")
            for row in reviews:
                row["major_errors"] = ["Synthetic extra factual error"]
            write_json(fixture[2] / "review.json", reviews)
            result = self.run_fixture(root, fixture)
            self.assertEqual(result["arms"]["rag_r01"]["penalized_point_score"], 0.5)

    def test_unscored_reviews_cannot_produce_scientific_results(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            fixture = self.fixture(root)
            reviews = p3.read(fixture[2] / "review.json")
            reviews[0]["reviewer_id"] = None
            write_json(fixture[2] / "review.json", reviews)
            with self.assertRaisesRegex(ValueError, "Incomplete identified"):
                self.run_fixture(root, fixture)
            self.assertFalse((root / "docs/P3_RESULTS.json").exists())

    def test_original_generation_mutation_is_detected(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            fixture = self.fixture(root)
            path = next(fixture[1].glob("P3-*.json"))
            path.write_text("{}")
            with self.assertRaisesRegex(ValueError, "generation record changed"):
                self.run_fixture(root, fixture)


if __name__ == "__main__":
    unittest.main()
