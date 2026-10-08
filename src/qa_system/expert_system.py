import os
from pathlib import Path

from config.settings import resolve_path
from src.api_integration.guarded_generator import (
    GuardedAnswerGenerator as DeepSeekAnswerGenerator,
)
from src.api_integration.prompt_builder import prepare_prompt
from src.knowledge_base.retriever import Retriever
from src.qa_system.citation_analyzer import CitationAnalyzer
from src.qa_system.evidence_policy import generation_decision
from src.qa_system.response_formatter import ResponseFormatter
from src.utils.artifacts import ArtifactRun, sha256_file, write_json
from src.utils.logger import logger


class ChemicalQAExpert:
    def __init__(self, *, reranker_profile=None, context_policy=None):
        if (reranker_profile is None) != (context_policy is None):
            raise ValueError(
                "Candidate QA requires both reranker profile and context policy"
            )
        self.retriever = (
            Retriever(reranker_profile=reranker_profile)
            if reranker_profile is not None
            else Retriever()
        )
        self.context_policy = None
        self.candidate_provenance = None
        if context_policy is not None:
            import json

            from src.qa_system.context_selection import validate_policy

            self.context_policy = json.loads(resolve_path(context_policy).read_text())
            validate_policy(self.context_policy)
            profile_path = resolve_path(reranker_profile)
            self.candidate_provenance = {
                "reranker_profile": str(profile_path),
                "reranker_profile_sha256": sha256_file(profile_path),
                "reranker_run_sha256": sha256_file(profile_path.parent / "run.json"),
            }
        self.generator = DeepSeekAnswerGenerator()
        self.formatter = ResponseFormatter()
        self.citation_analyzer = CitationAnalyzer()
        logger.info("System initialized!")

    def answer_query(self, question: str, analyze_citations: bool = True) -> str:
        """回答用户问题"""
        # 检索相关上下文
        selection_record = None
        if getattr(self, "context_policy", None) is not None:
            from src.qa_system.context_selection import select_context

            selection = select_context(
                question,
                self.retriever.search(
                    question, self.context_policy["candidate_window"]
                ),
                self.context_policy,
                self.generator.api_handler.request_parameters()["body"],
                template=self.generator.prompt_template,
            )
            prepared = selection.prepared
            selection_record = selection.audit
        else:
            context = self.retriever.retrieve_relevant_context(
                question, return_dict_list=True
            )
            prepared = prepare_prompt(
                question, context, template=self.generator.prompt_template
            )
        context = prepared.chunks
        # Generation and auditing use the same normalized evidence snapshot.
        result = self.generator.generate_answer_result(question, prepared)
        generation_input = {
            **prepared.record(),
            "prompt_sent": result.request_sent,
            "decision": generation_decision(context),
            "context_selection": selection_record,
            "candidate_retrieval": getattr(self, "candidate_provenance", None),
            "runtime_freeze": getattr(self, "runtime_provenance", None),
            "answer_validation": getattr(self.generator, "last_validation", None),
        }
        fingerprint = getattr(self.retriever.vector_store, "index_sha256", None)
        provenance = {
            "index_sha256": fingerprint if isinstance(fingerprint, str) else None,
            "question": question,
        }
        with ArtifactRun("qa") as run:
            record = {
                "question": question,
                "raw_answer": result.content,
                "generation_input": generation_input,
                "generation_result": result.record(),
            }
            if not result.completed:
                write_json(run.path / "failure.json", record)
                self.last_run_dir = run.publish(result.status, provenance)
                logger.info("Failed generation saved to %s", self.last_run_dir)
                result.require_content()
            raw_answer = result.require_content()
            if analyze_citations and context:
                self._analyze_citations(
                    raw_answer, context, run.path / "citation_analysis.txt"
                )
            formatted_response = self.formatter.format(
                question, raw_answer, context, allow_legacy=False
            )
            mapping = self.formatter.format_answer(
                raw_answer, context, allow_legacy=False
            )
            record.update(
                evidence_map=mapping["evidence_map"],
                unresolved_citations=mapping["unresolved_citations"],
            )
            self._save_answer(formatted_response, record, run.path)
            self.last_run_dir = run.publish(
                result.status,
                provenance,
            )
        logger.info("Run saved to %s", self.last_run_dir)
        return formatted_response

    def _analyze_citations(self, answer: str, context: list, output_file: Path):
        analysis_report = self.citation_analyzer.analyze_citations(
            answer, context, allow_legacy=False
        )
        self.citation_analyzer.print_detailed_report(analysis_report)
        self.citation_analyzer.save_analysis_to_file(analysis_report, str(output_file))

    def _save_answer(self, answer: str, evidence_record: dict, directory: Path):
        (directory / "answer.md").write_text(answer, encoding="utf-8")
        write_json(directory / "answer.evidence.json", evidence_record)

    def analyze_existing_answer(self, answer_file: str):
        """分析现有答案文件的引用情况"""
        try:
            answer_file = str(resolve_path(answer_file))
            # 检查文件是否存在
            if not os.path.exists(answer_file):
                logger.error(f"答案文件不存在: {answer_file}")
                return None

            # 读取答案文件
            with open(answer_file, "r", encoding="utf-8") as f:
                answer_content = f.read()

            # 提取问题分析部分
            import re

            analysis_match = re.search(
                r"## 问题分析\n(.*?)\n\n## 参考文献", answer_content, re.DOTALL
            )

            if not analysis_match:
                logger.error("无法从答案文件中提取问题分析内容")
                return None

            analysis = analysis_match.group(1).strip()

            # 由于无法从格式化后的答案中恢复原始上下文，
            # 这里提供一个简化的分析，只统计引用标记
            logger.info("分析现有答案文件的引用情况")

            # 提取所有引用标记
            citations = re.findall(r"\[(\d+)\]", analysis)
            unique_citations = list(set(citations))

            print("\n引用分析结果:")
            print(f"总引用次数: {len(citations)}")
            print(f"唯一引用数: {len(unique_citations)}")
            print(f"引用的文献编号: {sorted(unique_citations, key=int)}")

            return {
                "total_citations": len(citations),
                "unique_citations": len(unique_citations),
                "citation_numbers": sorted(unique_citations, key=int),
            }

        except Exception:
            logger.exception("分析现有答案失败")
            return None
