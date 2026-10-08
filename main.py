import argparse

from config.settings import configure_paths
from src.api_integration.result import APIGenerationError
from src.qa_system.expert_system import ChemicalQAExpert


def main():
    # 命令行界面
    parser = argparse.ArgumentParser(
        description="Organic Electrocatalysis QA Expert System"
    )
    parser.add_argument(
        "-q", "--question", help="Your research question about organic electrocatalysis"
    )
    parser.add_argument(
        "--index-dir", help="Index directory, relative to project root or absolute"
    )
    parser.add_argument("--output-dir", help="Root for isolated question runs")
    parser.add_argument(
        "--runtime-profile",
        choices=["legacy", "hybrid_rerank", "hybrid_rerank_diverse"],
        help="Explicit frozen local runtime (candidate profiles are experimental)",
    )
    parser.add_argument(
        "--check-runtime", action="store_true", help="Verify freeze offline and exit"
    )
    args = parser.parse_args()
    if args.check_runtime and not args.runtime_profile:
        parser.error("--check-runtime requires --runtime-profile")
    if args.runtime_profile and args.index_dir:
        parser.error("Frozen runtime cannot be combined with --index-dir")
    expert_options = {}
    runtime_provenance = None
    if args.runtime_profile:
        from src.qa_system.runtime_profile import configure_runtime, validate_runtime

        try:
            if args.check_runtime:
                _, _, provenance = validate_runtime(args.runtime_profile)
                print(f"Runtime verified: {provenance['profile']}")
                return
            expert_options, runtime_provenance = configure_runtime(args.runtime_profile)
        except (ValueError, KeyError, OSError) as exc:
            parser.error(str(exc))
    configure_paths(index_dir=args.index_dir, output_dir=args.output_dir)

    # Parse help before initializing models and the index.
    expert = ChemicalQAExpert(**expert_options)
    expert.runtime_provenance = runtime_provenance

    if args.question:
        # 命令行模式
        try:
            response = expert.answer_query(args.question)
        except APIGenerationError as exc:
            print(f"回答生成未完成 [{exc.result.error_code}]：{exc}")
            raise SystemExit(1) from None
        print("\n" + response)
    else:
        # 交互模式
        print("Organic Electrocatalysis QA Expert System (Type 'exit' to quit)")
        while True:
            question = input("\nYour question: ")
            if question.lower() in ["exit", "quit"]:
                break

            try:
                response = expert.answer_query(question)
            except APIGenerationError as exc:
                print(f"回答生成未完成 [{exc.result.error_code}]：{exc}")
                continue
            print("\n" + response)
            print("\n" + "=" * 80)


if __name__ == "__main__":
    main()

# What is Electrocatalysis?
