from typing import Any

from config.settings import resolve_path
from src.evaluation.citations import citation_statistics
from src.qa_system.evidence import citation_label, reference_pattern, resolve_citations
from src.utils.artifacts import atomic_text_writer
from src.utils.logger import logger


class CitationAnalyzer:
    """
    分析答案引用的上下文片段数量的工具类
    """

    def __init__(self):
        """初始化引用分析器"""

    def analyze_citations(
        self, answer: str, context: list[dict[str, Any]], *, allow_legacy: bool = True
    ) -> dict[str, Any]:
        """
        分析答案中的引用情况

        Args:
            answer: 原始答案文本
            context: 上下文片段列表

        Returns:
            包含引用分析结果的字典
        """
        logger.info("开始分析答案引用情况")

        # 1. 统计上下文片段总数
        total_context_chunks = len(
            resolve_citations(answer, context, allow_legacy=allow_legacy)["chunks"]
        )

        # 2. 提取答案中的所有引用标记
        citations_in_answer = self._extract_citations_from_answer(
            answer, allow_legacy=allow_legacy
        )

        # 3. 分析引用的上下文片段
        cited_chunks_analysis = self._analyze_cited_chunks(
            answer, context, allow_legacy=allow_legacy
        )

        # 4. 计算上下文片段使用率
        citation_coverage = self._calculate_coverage(
            cited_chunks_analysis, total_context_chunks
        )

        # 5. 生成详细报告
        analysis_report = {
            "total_context_chunks": total_context_chunks,
            "citations_in_answer": citations_in_answer,
            "cited_chunks_analysis": cited_chunks_analysis,
            "citation_coverage": citation_coverage,
            "citation_statistics": citation_statistics(answer, context),
            "unresolved_citations": cited_chunks_analysis["unresolved_citations"],
            "summary": self._generate_summary(cited_chunks_analysis, citation_coverage),
        }

        logger.info(
            f"引用分析完成: 总片段{total_context_chunks}个, 引用片段{citation_coverage['cited_count']}个"
        )
        return analysis_report

    def _extract_citations_from_answer(
        self, answer: str, *, allow_legacy: bool = True
    ) -> list[str]:
        """
        从答案中提取所有引用标记

        Args:
            answer: 答案文本

        Returns:
            引用标记列表
        """
        return sorted(
            {
                citation_label(m)
                for m in reference_pattern(allow_legacy).finditer(answer)
            }
        )

    def _analyze_cited_chunks(
        self, answer: str, context: list[dict[str, Any]], *, allow_legacy: bool = True
    ) -> dict[str, Any]:
        resolved = resolve_citations(answer, context, allow_legacy=allow_legacy)
        mapping = {}
        for i, doc in enumerate(resolved["chunks"]):
            count = resolved["counts"].get(doc["chunk_id"], 0)
            mapping[doc["chunk_id"]] = {
                "index": i,
                "doc_id": doc["doc_id"],
                "chunk_id": doc["chunk_id"],
                "source": doc["source"],
                "sources": doc["sources"],
                "chunk_index": doc["chunk_index"],
                "text_preview": doc["text"][:100] + "...",
                "cited": bool(count),
                "citation_count": count,
                "location_status": doc.get("location_status", "unavailable"),
                "page_numbers": doc.get("page_numbers", []),
                "source_spans": doc.get("source_spans", []),
            }
        cited = [doc for doc in mapping.values() if doc["cited"]]
        return {
            "total_chunks": len(mapping),
            "cited_chunks": cited,
            "cited_count": len(cited),
            "chunk_mapping": mapping,
            "unresolved_citations": resolved["unresolved"],
        }

    def _calculate_coverage(
        self, cited_chunks_analysis: dict[str, Any], total_chunks: int
    ) -> dict[str, Any]:
        """
        计算上下文片段使用率

        Args:
            cited_chunks_analysis: 引用分析结果
            total_chunks: 总片段数

        Returns:
            覆盖率统计
        """
        cited_count = cited_chunks_analysis["cited_count"]
        coverage_percentage = (
            (cited_count / total_chunks * 100) if total_chunks > 0 else 0
        )

        return {
            "cited_count": cited_count,
            "total_count": total_chunks,
            "coverage_percentage": round(coverage_percentage, 2),
            "unused_count": total_chunks - cited_count,
        }

    def _generate_summary(
        self, cited_chunks_analysis: dict[str, Any], coverage: dict[str, Any]
    ) -> str:
        """
        生成分析摘要

        Args:
            cited_chunks_analysis: 引用分析结果
            coverage: 覆盖率统计

        Returns:
            摘要文本
        """
        summary = "引用分析摘要:\n"
        summary += f"- 总上下文片段数: {coverage['total_count']}\n"
        summary += f"- 被引用的片段数: {coverage['cited_count']}\n"
        summary += f"- 未使用的片段数: {coverage['unused_count']}\n"
        summary += f"- 无法映射的引用标记数: {len(cited_chunks_analysis['unresolved_citations'])}\n"
        summary += f"- 上下文片段使用率: {coverage['coverage_percentage']}%\n"

        if cited_chunks_analysis["cited_chunks"]:
            summary += "- 被引用的片段来源: "
            sources = list(
                {chunk["source"] for chunk in cited_chunks_analysis["cited_chunks"]}
            )
            summary += ", ".join(sources[:5])  # 只显示前5个来源
            if len(sources) > 5:
                summary += f" 等{len(sources)}个来源"

        return summary

    def print_detailed_report(self, analysis_report: dict[str, Any]) -> None:
        """
        打印详细的分析报告

        Args:
            analysis_report: 分析报告
        """
        print("\n" + "=" * 60)
        print("答案引用上下文片段分析报告")
        print("=" * 60)

        # 基本信息
        print("\n📊 基本统计:")
        print(f"   总上下文片段数: {analysis_report['total_context_chunks']}")
        print(
            f"   被引用的片段数: {analysis_report['citation_coverage']['cited_count']}"
        )
        print(
            f"   上下文片段使用率: {analysis_report['citation_coverage']['coverage_percentage']}%"
        )

        # 引用详情
        if analysis_report["cited_chunks_analysis"]["cited_chunks"]:
            print("\n📚 被引用的片段详情:")
            for i, chunk in enumerate(
                analysis_report["cited_chunks_analysis"]["cited_chunks"], 1
            ):
                print(f"   {i}. 来源: {chunk['source']}")
                print(f"      片段索引: {chunk['chunk_index']}")
                print(f"      PDF 物理页码: {chunk['page_numbers'] or '未定位'}")
                print(f"      引用次数: {chunk['citation_count']}")
                print(f"      内容预览: {chunk['text_preview']}")
                print()

        # 未使用的片段
        unused_count = analysis_report["citation_coverage"]["unused_count"]
        if unused_count > 0:
            print("\n⚠️  未使用的片段:")
            print(f"   有 {unused_count} 个上下文片段未被引用")

            # 显示一些未使用的片段
            unused_chunks = []
            for chunk_info in analysis_report["cited_chunks_analysis"][
                "chunk_mapping"
            ].values():
                if not chunk_info["cited"]:
                    unused_chunks.append(chunk_info)

            for i, chunk in enumerate(unused_chunks[:3], 1):  # 只显示前3个
                print(f"   {i}. 来源: {chunk['source']}")
                print(f"      内容预览: {chunk['text_preview']}")
                print()

            if len(unused_chunks) > 3:
                print(f"   ... 还有 {len(unused_chunks) - 3} 个未使用的片段")

        # 摘要
        print("\n📋 分析摘要:")
        print(analysis_report["summary"])

        print("\n" + "=" * 60)

    def save_analysis_to_file(
        self, analysis_report: dict[str, Any], filename: str = "citation_analysis.txt"
    ) -> None:
        """
        将分析结果保存到文件

        Args:
            analysis_report: 分析报告
            filename: 文件名
        """
        with atomic_text_writer(resolve_path(filename)) as f:
            f.write("答案引用上下文片段分析报告\n")
            f.write("=" * 50 + "\n\n")

            # 写入摘要
            f.write(analysis_report["summary"] + "\n\n")

            # 写入详细统计
            f.write("详细统计:\n")
            f.write(f"总上下文片段数: {analysis_report['total_context_chunks']}\n")
            f.write(
                f"被引用的片段数: {analysis_report['citation_coverage']['cited_count']}\n"
            )
            f.write(
                f"上下文片段使用率: {analysis_report['citation_coverage']['coverage_percentage']}%\n\n"
            )

            # 写入被引用的片段详情
            if analysis_report["cited_chunks_analysis"]["cited_chunks"]:
                f.write("被引用的片段详情:\n")
                for i, chunk in enumerate(
                    analysis_report["cited_chunks_analysis"]["cited_chunks"], 1
                ):
                    f.write(f"{i}. 来源: {chunk['source']}\n")
                    f.write(f"   片段索引: {chunk['chunk_index']}\n")
                    f.write(f"   PDF 物理页码: {chunk['page_numbers'] or '未定位'}\n")
                    f.write(f"   引用次数: {chunk['citation_count']}\n")
                    f.write(f"   内容预览: {chunk['text_preview']}\n\n")

        logger.info(f"引用分析报告已保存到: {filename}")


def analyze_answer_citations(
    answer: str,
    context: list[dict[str, Any]],
    print_report: bool = True,
    save_to_file: bool = False,
) -> dict[str, Any]:
    """
    便捷函数：分析答案引用的上下文片段数量

    Args:
        answer: 答案文本
        context: 上下文片段列表
        print_report: 是否打印报告
        save_to_file: 是否保存到文件

    Returns:
        分析报告字典
    """
    analyzer = CitationAnalyzer()
    analysis_report = analyzer.analyze_citations(answer, context)

    if print_report:
        analyzer.print_detailed_report(analysis_report)

    if save_to_file:
        analyzer.save_analysis_to_file(analysis_report)

    return analysis_report
