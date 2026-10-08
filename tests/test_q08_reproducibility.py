"""Publication, path independence and immutable candidate regression checks."""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import numpy as np

from config.settings import BASE_DIR, configure_paths, resolve_path, settings
from qa_testing.direct_api_test import EnhancedAPITester
from qa_testing.test_organic_electrocatalysis_qa import OrganicElectrocatalysisQATester
from src.api_integration.api_generator import DeepSeekAnswerGenerator
from src.api_integration.result import APIGenerationError, GenerationResult
from src.knowledge_base.vector_store import VectorStore
from src.pipeline.vector_index_builder import VectorIndexBuilder
from src.qa_system.expert_system import ChemicalQAExpert
from src.qa_system.response_formatter import ResponseFormatter
from src.utils.artifacts import (
    ArtifactRun,
    atomic_text_writer,
    config_record,
    finish_session,
    sha256_file,
    write_json,
)
from tests.test_q01_identity import identified


class ReproducibilityTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.output = patch.object(settings, "OUTPUT_DIR", str(self.root / "outputs"))
        self.output.start()
        self.addCleanup(self.output.stop)

    def candidate(self):
        with ArtifactRun("indexes") as run:
            write_json(
                run.path / "vector_index.json",
                {
                    "documents": [identified("a.pdf", b"pdf", "evidence")],
                    "vectors": [[1.0, 0.0]],
                },
            )
            write_json(run.path / "processed_chunks.json", {"fixture": True})
            return run.publish(
                "ready",
                {
                    "files": {
                        name: sha256_file(run.path / name)
                        for name in ("vector_index.json", "processed_chunks.json")
                    }
                },
            )

    def test_atomic_write_failure_preserves_original_and_removes_temp(self):
        path = self.root / "answer.md"
        path.write_text("original")
        with self.assertRaises(OSError), atomic_text_writer(path) as handle:
            handle.write("partial")
            raise OSError("simulated disk failure")
        self.assertEqual(path.read_text(), "original")
        self.assertEqual(list(self.root.iterdir()), [path])

    def test_unpublished_directory_is_invisible_and_cleaned_on_failure(self):
        target = self.root / "new-run"
        with self.assertRaises(OSError), ArtifactRun("qa", destination=target) as run:
            (run.path / "answer.md").write_text("partial")
            self.assertFalse(target.exists())
            raise OSError("evidence write failed")
        self.assertFalse(target.exists())
        self.assertFalse(list(self.root.glob(".staging-*")))

    def test_existing_destination_is_never_overwritten(self):
        target = self.root / "existing"
        target.mkdir()
        (target / "sentinel").write_text("original")
        with self.assertRaises(FileExistsError):
            ArtifactRun("qa", destination=target)
        self.assertEqual((target / "sentinel").read_text(), "original")

    def test_candidate_load_checks_index_and_processed_hashes(self):
        for filename in ("vector_index.json", "processed_chunks.json"):
            with self.subTest(filename=filename):
                candidate = self.candidate()
                with patch.object(settings, "VECTOR_DB_DIR", str(candidate)):
                    store = VectorStore.__new__(VectorStore)
                    self.assertEqual(len(store._load_vector_index()["documents"]), 1)
                    with (candidate / filename).open("a") as handle:
                        handle.write(" ")
                    with self.assertRaisesRegex(ValueError, "checksum mismatch"):
                        store._load_vector_index()

    def test_non_ready_candidate_and_missing_index_fail_explicitly(self):
        candidate = self.candidate()
        record = json.loads((candidate / "run.json").read_text())
        record["status"] = "running"
        write_json(candidate / "run.json", record)
        store = VectorStore.__new__(VectorStore)
        with (
            patch.object(settings, "VECTOR_DB_DIR", str(candidate)),
            self.assertRaisesRegex(ValueError, "not ready"),
        ):
            store._load_vector_index()
        with (
            patch.object(settings, "VECTOR_DB_DIR", str(self.root)),
            self.assertRaises(FileNotFoundError),
        ):
            store._load_vector_index()

    def test_published_candidates_reject_incremental_mutation(self):
        candidate = self.candidate()
        store = VectorStore.__new__(VectorStore)
        store.model = Mock()
        with patch.object(settings, "VECTOR_DB_DIR", str(candidate)):
            with self.assertRaisesRegex(ValueError, "immutable"):
                store.add_documents([identified("b.pdf", b"other", "new evidence")])
            with self.assertRaisesRegex(ValueError, "immutable"):
                store._save_vector_index({"documents": [], "vectors": []})
        store.model.encode.assert_not_called()

    def test_validated_rebuild_publishes_pair_and_preserves_active_files(self):
        active = self.root / "active"
        active.mkdir()
        (active / "vector_index.json").write_text("old index")
        (active / "processed_chunks.json").write_text("old chunks")
        builder = VectorIndexBuilder.__new__(VectorIndexBuilder)
        builder.pdf_dir = "fixture"
        builder.vector_store = Mock()
        builder.vector_store.encode_texts.return_value = np.array([[1.0, 0.0]])
        builder.vector_store.budget.manifest.return_value = {}
        builder.process_documents = Mock(
            return_value=[identified("a.pdf", b"pdf", "evidence")]
        )
        with (
            patch.object(settings, "VECTOR_DB_DIR", str(active)),
            patch.object(settings, "PROCESSED_DIR", str(active)),
            patch(
                "scripts.validate_q03.validate", return_value={"fixture": True}
            ) as validate,
        ):
            target = builder.run_pipeline()
            self.assertEqual(validate.call_count, 1)
        record = json.loads((target / "run.json").read_text())
        for name, digest in record["files"].items():
            self.assertEqual(sha256_file(target / name), digest)
        self.assertEqual(record["status"], "ready")
        self.assertEqual((active / "vector_index.json").read_text(), "old index")
        self.assertEqual((active / "processed_chunks.json").read_text(), "old chunks")
        with self.assertRaises(FileExistsError):
            builder.run_pipeline(destination=target)

    def test_low_level_rebuild_requires_explicit_staging_directory(self):
        builder = VectorIndexBuilder.__new__(VectorIndexBuilder)
        with self.assertRaisesRegex(ValueError, "run_pipeline"):
            builder.save_processed_chunks([])

    def test_relative_paths_and_hf_cache_are_independent_of_cwd(self):
        code = (
            "import json,os; from config.settings import settings; "
            "print(json.dumps([settings.VECTOR_DB_DIR,settings.OUTPUT_DIR,os.environ['HF_HOME']]))"
        )
        env = {
            **os.environ,
            "PYTHONPATH": BASE_DIR,
            "CHEMQA_INDEX_DIR": "output/path-fixture",
            "CHEMQA_OUTPUT_DIR": "output/runs-fixture",
            "HF_HOME": "models/huggingface",
        }
        outputs = [
            subprocess.check_output(
                [sys.executable, "-c", code], cwd=cwd, env=env, text=True
            )
            for cwd in (BASE_DIR, self.root)
        ]
        self.assertEqual(outputs[0], outputs[1])
        self.assertEqual(
            json.loads(outputs[0])[0], str(Path(BASE_DIR) / "output/path-fixture")
        )

    def test_cli_overrides_take_precedence_and_share_bundle_directory(self):
        with (
            patch.object(settings, "VECTOR_DB_DIR"),
            patch.object(settings, "PROCESSED_DIR"),
        ):
            configure_paths(index_dir="output/candidate", output_dir="output/new-runs")
            self.assertEqual(
                settings.VECTOR_DB_DIR, str(resolve_path("output/candidate"))
            )
            self.assertEqual(settings.PROCESSED_DIR, settings.VECTOR_DB_DIR)
            self.assertEqual(settings.OUTPUT_DIR, str(resolve_path("output/new-runs")))

    def test_repeated_questions_and_failure_publish_distinct_complete_runs(self):
        expert = ChemicalQAExpert.__new__(ChemicalQAExpert)
        expert.retriever = Mock()
        expert.retriever.vector_store.index_sha256 = "fixture-index"
        expert.retriever.retrieve_relevant_context.return_value = []
        expert.generator = DeepSeekAnswerGenerator()
        expert.formatter = ResponseFormatter()
        with patch("src.api_integration.api_handler.requests.post") as post:
            paths = []
            for _ in range(2):
                expert.answer_query("same question", analyze_citations=False)
                paths.append(expert.last_run_dir)
            post.assert_not_called()
        self.assertNotEqual(paths[0], paths[1])
        previous = (paths[0] / "answer.md").read_bytes()
        with (
            patch.object(
                expert.generator,
                "generate_answer_result",
                return_value=GenerationResult(
                    status="failed",
                    error_code="fixture",
                    error_message="offline failure",
                ),
            ),
            self.assertRaises(APIGenerationError),
        ):
            expert.answer_query("same question", analyze_citations=False)
        failed = expert.last_run_dir
        self.assertNotIn(failed, paths)
        self.assertFalse((failed / "answer.md").exists())
        self.assertTrue((failed / "failure.json").is_file())
        self.assertEqual((paths[0] / "answer.md").read_bytes(), previous)
        manifest = json.loads((failed / "run.json").read_text())
        self.assertEqual(manifest["status"], "failed")
        self.assertEqual(manifest["index_sha256"], "fixture-index")

    def test_batch_sessions_are_distinct_and_have_completion_marker(self):
        with patch("qa_testing.test_organic_electrocatalysis_qa.ChemicalQAExpert"):
            sessions = [OrganicElectrocatalysisQATester().output_dir for _ in range(2)]
        sessions.extend(EnhancedAPITester().output_dir for _ in range(2))
        self.assertEqual(len(set(sessions)), 4)
        for path in sessions:
            self.assertEqual(
                json.loads((path / "run.json").read_text())["status"], "running"
            )
        finish_session(sessions[0], {"successful_tests": 0})
        self.assertEqual(
            json.loads((sessions[0] / "run.json").read_text())["status"], "complete"
        )

    def test_citation_report_write_failure_does_not_publish_answer(self):
        from src.qa_system.citation_analyzer import CitationAnalyzer

        evidence = identified("a.pdf", b"pdf", "evidence")
        expert = ChemicalQAExpert.__new__(ChemicalQAExpert)
        expert.retriever = Mock()
        expert.retriever.retrieve_relevant_context.return_value = [evidence]
        expert.generator = DeepSeekAnswerGenerator()
        expert.formatter = ResponseFormatter()
        expert.citation_analyzer = CitationAnalyzer()
        generation = GenerationResult(
            status="success", content=f"Answer [Ref {evidence['chunk_id']}]"
        )
        with (
            patch.object(
                expert.generator, "generate_answer_result", return_value=generation
            ),
            patch(
                "src.qa_system.citation_analyzer.atomic_text_writer",
                side_effect=OSError("disk failure"),
            ),
            self.assertRaisesRegex(OSError, "disk failure"),
        ):
            expert.answer_query("question", analyze_citations=True)
        self.assertFalse(list((self.root / "outputs" / "qa").iterdir()))

    def test_config_snapshot_does_not_copy_credentials_or_endpoint(self):
        with patch.dict(
            settings.DEEPSEEK_API_CONFIG,
            api_key="secret-sentinel",
            base_url="private-endpoint",
        ):
            serialized = json.dumps(config_record())
        self.assertNotIn("secret-sentinel", serialized)
        self.assertNotIn("private-endpoint", serialized)


if __name__ == "__main__":
    unittest.main()
