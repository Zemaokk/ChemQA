"""
增强版API提问测试脚本

添加智能重试机制解决服务器繁忙问题
"""

import json
import os
import sys
import time
from datetime import datetime

# 添加项目根目录到Python路径
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config.settings import configure_paths
from src.api_integration.api_handler import DeepSeekAPIHandler  # 确保路径正确
from src.api_integration.result import execution_status
from src.utils.artifacts import (
    atomic_text_writer,
    create_session,
    finish_session,
    write_json,
    write_text,
)


class EnhancedAPITester:
    """增强版API测试器（带智能重试）"""

    def __init__(self):
        self.api_handler = DeepSeekAPIHandler()
        self.results = []
        self.output_dir = create_session("direct_api_batches")

        # 定义10个有机电催化领域的问题
        self.questions = [
            "What are the key mechanisms of CO2 electroreduction on copper-based catalysts?",
            "How does the coordination environment affect the performance of nickel-based electrocatalysts for alcohol oxidation?",
            "What are the recent advances in electrochemical C-H functionalization of aromatic compounds?",
            "How can we improve the selectivity of electrochemical reduction of carbonyl compounds?",
            "What role do electrolyte additives play in organic electrocatalysis?",
            "How does the surface structure of platinum catalysts influence organic molecule oxidation?",
            "What are the challenges and solutions for electrochemical synthesis of heterocyclic compounds?",
            "How can we achieve high current density in organic electrosynthesis?",
            "What are the mechanistic insights into electrochemical oxidation of biomass-derived compounds?",
            "How does the pH of electrolyte affect the reaction pathways in organic electrocatalysis?",
        ]

        # 提示词模板
        self.prompt_template = """请按照以下结构组织你的回答：

1. 回答摘要
- 简明扼要地总结关键发现和结论
- 突出最重要的数据和机制

2. 技术细节
- 详细解释反应机理和催化过程
- 分析关键参数和影响因素
- 讨论催化剂结构和性能关系
- 提供相关数据支持

3. 实际应用
- 讨论工业应用前景
- 分析技术优势和局限性
- 提出可能的优化方向

4. 局限性/研究空白
- 指出当前研究的不足
- 提出需要进一步研究的问题

注意事项：
1. 严格基于文献信息回答
2. 使用专业术语，但确保解释清晰
3. 引用具体的数据和文献

问题：{question}

请开始你的专业分析："""

    def run_single_test_with_retry(
        self, question: str, question_id: int, max_retries: int = 3
    ) -> dict:
        """带智能重试的单个API测试"""
        print(f"\n{'=' * 80}")
        print(f"增强测试 {question_id}/10: {question}")
        print(f"{'=' * 80}")

        started = time.perf_counter()
        full_prompt = self.prompt_template.format(question=question)
        generation = self.api_handler.generate_result(
            full_prompt, max_attempts=max_retries + 1
        )
        result = {
            "question_id": question_id,
            "question": question,
            "status": generation.status,
            "generation_result": generation.record(),
            "processing_time": round(time.perf_counter() - started, 2),
            "timestamp": datetime.now().astimezone().isoformat(),
            "method": "enhanced_api",
            "retries": max(generation.attempts - 1, 0),
        }
        if not generation.completed:
            result["error"] = generation.error_message
            write_json(
                self.output_dir / f"enhanced_failure_{question_id:02d}.json", result
            )
            return result
        answer = generation.require_content()
        result.update(answer=answer, answer_length=len(answer))
        write_text(
            self.output_dir / f"enhanced_answer_{question_id:02d}.md",
            f"# API 回答 - 问题 {question_id}\n\n**问题：** {question}\n\n{answer}\n",
        )
        write_text(self.output_dir / f"enhanced_raw_{question_id:02d}.txt", answer)
        return result

    def update_results(self, new_results: list):
        """更新结果集，只替换指定ID的结果"""
        # 创建结果索引
        result_map = {r["question_id"]: r for r in self.results}

        # 更新结果
        for new_result in new_results:
            qid = new_result["question_id"]
            result_map[qid] = new_result

        # 重建有序结果列表
        self.results = [result_map[i + 1] for i in range(len(self.questions))]

    def run_targeted_tests(self, question_ids: list):
        """运行指定问题的测试并更新结果"""
        print(f"🚀 开始运行指定问题测试: {question_ids}")

        # 加载现有结果（如果存在）
        summary_file = self.output_dir / "enhanced_api_summary.json"
        if summary_file.exists():
            with open(summary_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                self.results = data["detailed_results"]
            print(f"📂 已加载 {len(self.results)} 条现有结果")
        else:
            print("⚠️ 未找到现有结果文件，将创建新结果集")
            # 初始化空结果
            self.results = [
                {
                    "question_id": i + 1,
                    "question": self.questions[i],
                    "status": "pending",
                }
                for i in range(len(self.questions))
            ]

        # 运行指定问题的测试
        new_results = []
        for qid in question_ids:
            # 检查ID有效性
            if qid < 1 or qid > len(self.questions):
                print(f"⚠️ 忽略无效问题ID: {qid}")
                continue

            idx = qid - 1
            result = self.run_single_test_with_retry(
                question=self.questions[idx], question_id=qid
            )
            new_results.append(result)

        # 更新结果集
        self.update_results(new_results)

        # 保存更新后的结果
        self.save_summary_results()
        print(f"🎯 指定问题测试完成! 更新了 {len(question_ids)} 个问题的结果")

    def save_summary_results(self):
        """保存汇总结果（包含更新逻辑）"""
        # 计算统计信息
        successful_tests = [r for r in self.results if execution_status(r) == "success"]
        failed_tests = [
            r for r in self.results if execution_status(r) in ("failed", "truncated")
        ]
        unverified_tests = [
            r for r in self.results if execution_status(r) == "unverified"
        ]
        pending_tests = [
            r for r in self.results if "status" in r and r["status"] == "pending"
        ]

        # 计算平均指标
        processing_times = [
            r["processing_time"] for r in successful_tests if "processing_time" in r
        ]
        answer_lengths = [
            r["answer_length"] for r in successful_tests if "answer_length" in r
        ]

        avg_processing_time = (
            sum(processing_times) / len(processing_times) if processing_times else 0
        )
        avg_answer_length = (
            sum(answer_lengths) / len(answer_lengths) if answer_lengths else 0
        )

        # 构建汇总数据
        summary_data = {
            "test_info": {
                "total_questions": len(self.questions),
                "successful_tests": len(successful_tests),
                "failed_tests": len(failed_tests),
                "pending_tests": len(pending_tests),
                "unverified_tests": len(unverified_tests),
                "truncated_tests": sum(
                    execution_status(r) == "truncated" for r in self.results
                ),
                "timestamp": datetime.now().astimezone().isoformat(),
                "method": "enhanced_api",
            },
            "statistics": {
                "avg_processing_time": round(avg_processing_time, 2),
                "avg_answer_length": round(avg_answer_length, 1),
            },
            "detailed_results": self.results,
        }

        # 保存JSON文件
        json_file = self.output_dir / "enhanced_api_summary.json"
        with atomic_text_writer(json_file) as f:
            json.dump(summary_data, f, ensure_ascii=False, indent=2)

        # 保存文本格式的汇总报告
        report_file = self.output_dir / "enhanced_api_summary_report.txt"
        with atomic_text_writer(report_file) as f:
            f.write("增强API提问测试汇总报告\n")
            f.write("=" * 60 + "\n\n")

            f.write(
                f"测试时间: {datetime.now().astimezone().strftime('%Y-%m-%d %H:%M:%S')}\n"
            )
            f.write("测试方法: 增强API提问（带重试机制）\n")
            f.write(f"总问题数: {len(self.questions)}\n")
            f.write(f"成功测试: {len(successful_tests)}\n")
            f.write(f"失败测试: {len(failed_tests)}\n")
            f.write(f"待测试: {len(pending_tests)}\n")
            f.write(f"历史状态未核实: {len(unverified_tests)}\n\n")

            f.write("统计信息:\n")
            f.write(f"- 平均处理时间: {avg_processing_time:.2f} 秒\n")
            f.write(f"- 平均答案长度: {avg_answer_length:.1f} 字符\n\n")

            f.write("详细结果:\n")
            for result in self.results:
                f.write(f"\n问题 {result['question_id']}: {result['question']}\n")
                if execution_status(result) in ("failed", "truncated"):
                    f.write(f"状态: 失败 (重试次数: {result.get('retries', 0)})\n")
                    f.write(f"错误信息: {result['error']}\n")
                elif execution_status(result) == "success":
                    f.write(f"状态: 成功 (重试次数: {result.get('retries', 0)})\n")
                    f.write(f"处理时间: {result['processing_time']} 秒\n")
                    f.write(f"答案长度: {result['answer_length']} 字符\n")
                else:
                    f.write(f"状态: {execution_status(result)}\n")

        finish_session(self.output_dir, summary_data["test_info"])

        # 打印汇总信息
        print("\n📊 测试汇总:")
        print(f"   成功: {len(successful_tests)}/{len(self.questions)}")
        print(f"   失败: {len(failed_tests)}/{len(self.questions)}")
        print(f"   待测: {len(pending_tests)}/{len(self.questions)}")
        print(f"   平均处理时间: {avg_processing_time:.2f} 秒")
        print(f"   平均答案长度: {avg_answer_length:.1f} 字符")


def main():
    """主函数"""
    print("🧪 增强版API提问测试脚本")
    print("=" * 60)
    print("🔄 添加智能重试机制解决服务器繁忙问题")

    import argparse

    parser = argparse.ArgumentParser(
        description="Run a batch in a new isolated directory"
    )
    parser.add_argument("--output-dir")
    parser.add_argument("--index-dir")
    args = parser.parse_args()
    configure_paths(index_dir=args.index_dir, output_dir=args.output_dir)

    # 创建测试器
    tester = EnhancedAPITester()

    # 指定需要重新运行的问题ID
    target_ids = [1]  # 问题1

    # 运行指定问题的测试
    tester.run_targeted_tests(target_ids)


if __name__ == "__main__":
    main()
