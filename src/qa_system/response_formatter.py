import os
import re
from datetime import datetime
from typing import Any

from config.settings import settings
from src.qa_system.evidence import citation_label, reference_pattern, resolve_citations
from src.utils.logger import logger


class ResponseFormatter:
    def __init__(self):
        self.system_domain = settings.DOMAIN

    def format(
        self,
        question: str,
        answer: str,
        context: list[dict[str, Any]],
        *,
        allow_legacy: bool = True,
    ) -> str:
        """格式化响应"""

        # 使用format_answer方法处理引用和参考文献
        formatted = self.format_answer(answer, context, allow_legacy=allow_legacy)

        # 构建响应头
        response = "# 有机电催化专家系统\n\n"
        response += f"**问题：** {question}\n\n"
        response += (
            f"**回答日期：** {datetime.now().astimezone().strftime('%Y-%m-%d %H:%M')}\n"
        )
        response += f"**模型：** {settings.DEEPSEEK_API_CONFIG['model']}\n\n"

        # 添加主要回答
        response += f"## 问题分析\n{formatted['formatted_answer']}\n\n"

        # 添加参考文献
        response += f"## 参考文献\n{chr(10).join(formatted['citations']) if formatted['citations'] else '无'}\n\n"

        # 添加上下文摘要
        if formatted["evidence_map"]:
            response += (
                f"*本次检索提供了{formatted['num_references']}篇文献的"
                f"{len(formatted['evidence_map'])}个片段；"
                "检索命中与引用定位不代表这些材料支持全部结论。*\n\n"
            )
        else:
            response += "*本次未检索到符合筛选条件的证据片段。*\n\n"

        response += "## 证据身份映射\n"
        for evidence in formatted["evidence_map"]:
            response += (
                f"- [{evidence['reference_number']}] `{evidence['chunk_id']}` "
                f"（文献 `{evidence['doc_id']}`，局部片段 {evidence['chunk_index']}）\n"
            )
            if evidence.get("location_status") == "located":
                for span in evidence["source_spans"]:
                    response += (
                        f"  PDF 第 {span['page_number']} 页；提取文本字符 "
                        f"[{span['char_start']}, {span['char_end']})。原文预览：\n\n"
                    )
                    preview = span["raw_text"][:200]
                    if len(span["raw_text"]) > 200:
                        preview += "…（完整片段见 evidence JSON）"
                    response += (
                        "\n".join("> " + line for line in preview.splitlines()) + "\n\n"
                    )
            else:
                response += "  PDF 页码未定位；不提供推测位置。\n"
        if formatted["unresolved_citations"]:
            response += (
                "\n*部分引用标记无法唯一定位，正文已标记；未将其计为有效片段引用。*\n"
            )
        response += "\n"

        # 添加响应结束标记
        response += "---\n"
        response += (
            "*回答由有机电催化专家系统生成，使用DeepSeek AI和专业的有机电催化知识库。*"
        )

        logger.info("已格式化用户响应")
        return response

    def format_answer(
        self, answer: str, context: list[dict[str, Any]], *, allow_legacy: bool = True
    ) -> dict:
        resolved = resolve_citations(answer, context, allow_legacy=allow_legacy)
        docs = resolved["chunks"]
        doc_numbers = {}
        representatives = {}
        evidence_map = []
        for doc in docs:
            did = doc["doc_id"]
            if did not in doc_numbers:
                doc_numbers[did] = len(doc_numbers) + 1
                representatives[did] = doc
            evidence_map.append({**doc, "reference_number": doc_numbers[did]})
        by_chunk = {doc["chunk_id"]: doc for doc in docs}

        def replace_ref(match):
            candidates = resolved["aliases"].get(citation_label(match), [])
            if len(candidates) == 1:
                return f"[{doc_numbers[by_chunk[candidates[0]]['doc_id']]}]"
            return f"【未解析引用：{match.group(0)}】"

        formatted_answer = reference_pattern(allow_legacy).sub(replace_ref, answer)
        # Existing generated bibliography cleanup remains separate from identity mapping.
        bib_pattern = r"(\*\*引用文献\*\*|\*\*参考文献\*\*|\*\*引用标注\*\*|引用文献|参考文献|引用标注)[^#\n]*((\n|.)*?)(?=(\n##|\n#|\Z))"
        formatted_answer = re.sub(bib_pattern, "", formatted_answer, flags=re.MULTILINE)
        formatted_answer = re.sub(r"([^\n])\n([^\n])", r"\1  \n\2", formatted_answer)
        formatted_answer = re.sub(r"(- .*?)(\n|$)", r"\1  \n", formatted_answer)
        citations = [
            f"[{number}] {os.path.splitext(os.path.basename(representatives[did]['source']))[0]} "
            f"(doc_id: {did})  "
            for did, number in doc_numbers.items()
        ]
        return {
            "formatted_answer": formatted_answer,
            "citations": citations,
            "num_references": len(doc_numbers),
            "evidence_map": evidence_map,
            "unresolved_citations": resolved["unresolved"],
        }
