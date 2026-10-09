"""Freeze fresh P3 questions, preview once, execute only the approved exact preview."""

import argparse
import json
import random
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter

import numpy as np
import pymupdf

from config.answer_policy import ANSWER_POLICY_VERSION, CONSERVATIVE_PROMPT
from config.settings import BASE_DIR
from src.api_integration.api_handler import DeepSeekAPIHandler
from src.api_integration.prompt_builder import PreparedPrompt, prepare_prompt
from src.qa_system.answer_validation import audit_answer
from src.qa_system.context_selection import select_context, verify_budget
from src.qa_system.runtime_profile import configure_runtime, validate_runtime
from src.utils.artifacts import ArtifactRun, sha256_file, write_json

ROOT = Path(BASE_DIR)
DATA = ROOT / "evaluation/p3"
PROTOCOL = ROOT / "config/p3_experiment.json"
ARMS = ("direct", "rag_r01")
SEED = 20261008
DIRECT_PROMPT = """你是电化学文献问答助手，领域为{domain}。
没有提供外部检索文献，请依据已有知识简短回答用户实际询问的内容。
不确定论文特定事实时明确说明无法确认，不猜测数值、工况或反应式；
不要把一般知识写成指定论文的实验结果，不编造参考文献或页码。
逐项保留已知数值的单位、正负号、参比和工况；不添加未询问的性能数字。
区分结果与机理解释，不将知识不足写成全文没有证据。
问题：{question}
"""


def read(path):
    return json.loads(Path(path).read_text())


def validate_sources():
    dataset, catalog = read(DATA / "questions.json"), read(DATA / "documents.json")
    excluded = set(read(DATA / "exclusions.json")["excluded_doc_ids"])
    questions, documents = dataset["questions"], catalog["documents"]
    if len(questions) != 30 or len(documents) != 20:
        raise ValueError("Expected 30 questions on 20 documents")
    if len({q["question_id"] for q in questions}) != 30:
        raise ValueError("Duplicate question")
    pages, identities, groups = {}, set(), set()
    for key, doc in documents.items():
        path = ROOT / doc["source"]
        identity = "doc_" + sha256_file(path)
        if identity != doc["doc_id"] or identity in excluded or identity in identities:
            raise ValueError("Changed, repeated or previously exposed PDF")
        identities.add(identity)
        with pymupdf.open(path) as pdf:
            pages[key] = [p.get_text() for p in pdf]
    for q in questions:
        if not q["answer_points"] or not q["must_not_claim"]:
            raise ValueError("Missing gold points or boundaries")
        for anchor in q["evidence"]:
            key = anchor["document_key"]
            text = pages[key][anchor["page_number"] - 1]
            if (
                text[anchor["char_start"] : anchor["char_end"]] != anchor["quote"]
                or anchor["doc_id"] != documents[key]["doc_id"]
                or q["article_group"] != documents[key]["article_id"]
            ):
                raise ValueError("Changed source anchor or article group")
            groups.add(q["article_group"])
    if len(groups) != 20:
        raise ValueError("Expected 20 independent article groups")
    return questions, documents


def freeze():
    if PROTOCOL.exists():
        raise FileExistsError("Protocol already frozen; do not overwrite")
    questions, documents = validate_sources()
    manifest, _, _ = validate_runtime("hybrid_rerank")
    protocol = {
        "schema": "chemqa-p3-protocol-v1",
        "created_utc": datetime.now(UTC).isoformat(),
        "source_development_commit": "b469d83",
        "questions": len(questions),
        "article_groups": len(documents),
        "arms": list(ARMS),
        "repetitions": 3,
        "maximum_requests": 180,
        "schedule_seed": SEED,
        "bootstrap_resamples": 10000,
        "runtime_profile": "hybrid_rerank",
        "request_body": manifest["generation"]["body"],
        "endpoint": manifest["generation"]["base_url"] + "/chat/completions",
        "max_attempts": 1,
        "direct_template": DIRECT_PROMPT,
        "rag_prompt_version": ANSWER_POLICY_VERSION,
        "context_policy": read(ROOT / "config/q065j_context.json"),
        "data_sha256": {p.name: sha256_file(p) for p in sorted(DATA.iterdir())},
        "implementation_sha256": {
            str(p.relative_to(ROOT)): sha256_file(p)
            for p in [
                ROOT / "scripts/run_p3_experiment.py",
                ROOT / "config/answer_policy.py",
                ROOT / "config/r01_runtime.json",
            ]
        },
        "evaluation_identity": "assistant exploratory review; user adjudicates disputes",
        "scientific_winner_predeclared": False,
    }
    write_json(PROTOCOL, protocol)
    print("Frozen 30 questions / 20 article groups; no ranking or API request")


def check_protocol():
    p = read(PROTOCOL)
    if p["arms"] != list(ARMS) or p["repetitions"] != 3 or p["maximum_requests"] != 180:
        raise ValueError("Unexpected experimental design")
    for name, checksum in p["data_sha256"].items():
        if sha256_file(DATA / name) != checksum:
            raise ValueError("Dataset changed after freeze")
    for name, checksum in p["implementation_sha256"].items():
        if sha256_file(ROOT / name) != checksum:
            raise ValueError("Implementation changed after freeze")
    validate_sources()
    validate_runtime(p["runtime_profile"])
    return p


def restore(row):
    r = row["generation_input"]
    return PreparedPrompt(
        question=row["question"],
        text=r["prompt"],
        serialized_context=r["serialized_context"],
        evidence_json=json.dumps(row["evidence"], ensure_ascii=False),
        template_sha256=r["template_sha256"],
        domain=r["domain"],
        budget_json=json.dumps(r["request_budget"], ensure_ascii=False),
        prompt_version=r["prompt_version"],
    )


def preview():
    p = check_protocol()
    marker = ROOT / "output/P3_PREVIEW_STARTED.json"
    with marker.open("x") as handle:
        json.dump({"protocol_sha256": sha256_file(PROTOCOL)}, handle)
    options, _ = configure_runtime(p["runtime_profile"])
    from src.knowledge_base.retriever import Retriever

    retriever = Retriever(reranker_profile=options["reranker_profile"])
    questions, _ = validate_sources()
    rows = []
    with ArtifactRun("p3_previews") as run:
        try:
            for q in questions:
                start = perf_counter()
                hits = retriever.search(q["question"], 50)
                seconds = perf_counter() - start
                write_json(
                    run.path / (q["question_id"] + "-retrieval.json"),
                    {"hits": hits, "elapsed_seconds": seconds},
                )
                for arm in ARMS:
                    selected = select_context(
                        q["question"],
                        hits if arm == "rag_r01" else [],
                        p["context_policy"],
                        p["request_body"],
                        template=CONSERVATIVE_PROMPT
                        if arm == "rag_r01"
                        else DIRECT_PROMPT,
                    )
                    prepared = selected.prepared
                    rows.append(
                        {
                            "question_id": q["question_id"],
                            "arm": arm,
                            "question": q["question"],
                            "article_group": q["article_group"],
                            "generation_input": prepared.record(),
                            "evidence": prepared.chunks,
                            "selection": selected.audit,
                            "retrieval_seconds": seconds if arm == "rag_r01" else 0.0,
                        }
                    )
                print(q["question_id"] + " frozen; no API request", flush=True)
            write_json(run.path / "requests.json", rows)
            files = {f.name: sha256_file(f) for f in run.path.glob("*.json")}
            target = run.publish(
                "ready", {"protocol_sha256": sha256_file(PROTOCOL), "files": files}
            )
        except BaseException:
            run.publish("interrupted", {"protocol_sha256": sha256_file(PROTOCOL)})
            raise
    verify_preview(target)
    sending_scope(target)
    print(target)


def verify_preview(directory):
    p = check_protocol()
    run = read(directory / "run.json")
    if run["status"] != "ready" or run["protocol_sha256"] != sha256_file(PROTOCOL):
        raise ValueError("Preview is not ready or protocol changed")
    for name, checksum in run["files"].items():
        if sha256_file(directory / name) != checksum:
            raise ValueError("Preview file changed")
    rows = read(directory / "requests.json")
    questions = {
        q["question_id"]: q for q in read(DATA / "questions.json")["questions"]
    }
    expected_pairs = {(qid, arm) for qid in questions for arm in ARMS}
    if (
        len(rows) != 60
        or {(r["question_id"], r["arm"]) for r in rows} != expected_pairs
    ):
        raise ValueError("Missing or repeated preview combinations")
    for row in rows:
        if row["question"] != questions[row["question_id"]]["question"]:
            raise ValueError("Question changed")
        if row["arm"] == "direct" and row["evidence"]:
            raise ValueError("Direct baseline contains evidence")
        expected = prepare_prompt(
            row["question"],
            row["evidence"],
            template=CONSERVATIVE_PROMPT if row["arm"] == "rag_r01" else DIRECT_PROMPT,
        )
        prepared = restore(row)
        if (
            prepared.text != expected.text
            or prepared.template_sha256 != expected.template_sha256
            or prepared.prompt_version != expected.prompt_version
            or prepared.serialized_context != expected.serialized_context
        ):
            raise ValueError("Prompt/context replay differs")
        if prepared.budget["policy"] != p["context_policy"]:
            raise ValueError("Context policy changed")
        verify_budget(prepared, p["request_body"])
    return rows


def sending_scope(directory):
    rows = verify_preview(directory)
    documents = {c["doc_id"] for r in rows for c in r["evidence"]}
    chunks = {c["chunk_id"] for r in rows for c in r["evidence"]}
    text = [
        "# P3 本轮第三方发送预览",
        "",
        "尚未发送。目的：补充文献特定问答对照实验；助手评审、用户复核争议。",
        "",
        f"预览目录：`{directory.relative_to(ROOT)}`",
        f"批准绑定的run.json SHA-256：`{sha256_file(directory / 'run.json')}`",
        "",
        f"30道新问题，20个目标文章组；两方案各3次，最多180次单次尝试。RAG实际输入涉及{len(documents)}份PDF身份、{len(chunks)}个不同片段（不发送整份PDF）。Direct仅发送问题与无检索提示。每次最多4096输出tokens，总输出上限737,280tokens，另有输入tokens费用，价格未核实。",
        "",
        "地址：https://llmapi.paratera.com/v1/chat/completions；DeepSeek-V4-Flash，thinking disabled，temperature0.3。不发送标准答案、评分要点、完整PDF、密钥文件或本地绝对路径，实际字段以冻结requests.json中的prompt为准；上下文包含来源标题、位置及片段。",
        "",
        "下面列出全部问题；每题所选原文与精确请求在requests.json，可在批准前逐项核查。排名不会在执行时重算，失败不自动补跑。",
        "",
    ]
    for row in rows:
        if row["arm"] == "rag_r01":
            text += [
                f"## {row['question_id']}",
                row["question"],
                "",
                *[
                    f"- {c['chunk_id']} | {c.get('source_title', Path(c['source']).name)} | PDF页 {c.get('page_numbers')}"
                    for c in row["evidence"]
                ],
                "",
            ]
    scope_note = ROOT / "output/P3_SEND_SCOPE.md"
    scope_note.parent.mkdir(parents=True, exist_ok=True)
    scope_note.write_text("\n".join(text))


def execute(directory, approved):
    rows = verify_preview(directory)
    if approved != sha256_file(directory / "run.json"):
        raise ValueError("Approval does not bind this exact preview")
    p = read(PROTOCOL)
    configure_runtime(p["runtime_profile"])
    handler = DeepSeekAPIHandler()
    if handler.request_parameters()["body"] != p["request_body"]:
        raise ValueError("Effective generation parameters changed")
    marker = ROOT / "output/P3_GENERATION_STARTED.json"
    with marker.open("x") as handle:
        json.dump({"preview_sha256": approved}, handle)
    schedule = [(row, repetition) for row in rows for repetition in range(1, 4)]
    random.Random(SEED).shuffle(schedule)
    with ArtifactRun("p3_generations") as run:
        try:
            for row, repetition in schedule:
                key = f"{row['question_id']}-{row['arm']}-r{repetition}"
                write_json(
                    run.path / (key + ".intent.json"),
                    {
                        "request_key": key,
                        "state": "attempt_started",
                        "preview_sha256": approved,
                    },
                )
                prepared = restore(row)
                if row["arm"] == "rag_r01" and not row["evidence"]:
                    from src.api_integration.result import GenerationResult

                    result = GenerationResult(
                        status="no_evidence", content="当前检索未取得可用证据。"
                    )
                else:
                    result = handler.generate_result(prepared.text, prepared=prepared)
                guard = (
                    audit_answer(row["question"], result.content, row["evidence"])
                    if row["arm"] == "rag_r01" and result.status == "success"
                    else None
                )
                write_json(
                    run.path / (key + ".json"),
                    {
                        **row,
                        "repetition": repetition,
                        "result": result.record(),
                        "answer": result.content,
                        "answer_validation": guard,
                    },
                )
                print(key + ": " + result.status, flush=True)
            files = {f.name: sha256_file(f) for f in run.path.glob("*.json")}
            target = run.publish(
                "complete",
                {
                    "preview_sha256": approved,
                    "protocol_sha256": sha256_file(PROTOCOL),
                    "files": files,
                },
            )
        except BaseException:
            run.publish(
                "interrupted",
                {"preview_sha256": approved, "automatic_resume_allowed": False},
            )
            raise
    create_review(target)
    print(target)


def load_results(directory):
    run = read(directory / "run.json")
    if run["status"] != "complete" or run["protocol_sha256"] != sha256_file(PROTOCOL):
        raise ValueError("Incomplete or different generation campaign")
    for name, checksum in run["files"].items():
        if sha256_file(directory / name) != checksum:
            raise ValueError("Original generation record changed")
    rows = [
        (f.name, read(f))
        for f in directory.glob("P3-*.json")
        if not f.name.endswith(".intent.json")
    ]
    questions = read(DATA / "questions.json")["questions"]
    expected = {
        (q["question_id"], arm, rep)
        for q in questions
        for arm in ARMS
        for rep in range(1, 4)
    }
    actual = {(row["question_id"], row["arm"], row["repetition"]) for _, row in rows}
    if len(rows) != 180 or actual != expected:
        raise ValueError("Expected 180 immutable question/arm/repetition results")
    return rows


def create_review(directory):
    records = load_results(directory)
    random.Random(SEED + 1).shuffle(records)
    keys, review = {}, []
    for n, (name, row) in enumerate(records, 1):
        rid = f"B{n:03d}"
        keys[rid] = {"filename": name, "sha256": sha256_file(directory / name)}
        review.append(
            {
                "review_id": rid,
                "question_id": row["question_id"],
                "question": row["question"],
                "answer": row["answer"],
                "technical_status": row["result"]["status"],
                "reviewer_id": None,
                "reviewer_kind": None,
                "point_correct": None,
                "point_reasons": None,
                "major_errors": None,
                "claims": None,
                "review_notes": [],
            }
        )
    with ArtifactRun("p3_reviews") as run:
        write_json(run.path / "mapping.json", keys)
        write_json(run.path / "review.json", review)
        target = run.publish(
            "pending_review",
            {
                "generation_directory": str(directory.relative_to(ROOT)),
                "generation_run_sha256": sha256_file(directory / "run.json"),
            },
        )
    print("Anonymous review (not independently blinded): " + str(target))


def paired_bootstrap(values, *, samples=10000, seed=SEED):
    delta = np.asarray(values, dtype=float)
    if delta.ndim != 1 or not len(delta) or not np.isfinite(delta).all():
        raise ValueError("Finite paired article-group differences required")
    rng = np.random.default_rng(seed)
    means = delta[rng.integers(0, len(delta), size=(samples, len(delta)))].mean(axis=1)
    return {
        "difference_pp": float(delta.mean() * 100),
        "ci95_pp": [float(v * 100) for v in np.quantile(means, [0.025, 0.975])],
        "article_groups": len(delta),
    }


def report(directory):
    check_protocol()
    review = read(directory / "review.json")
    mapping = read(directory / "mapping.json")
    run = read(directory / "run.json")
    generation = ROOT / run["generation_directory"]
    if sha256_file(generation / "run.json") != run["generation_run_sha256"]:
        raise ValueError("Review source changed")
    originals = dict(load_results(generation))
    questions = {
        q["question_id"]: q for q in read(DATA / "questions.json")["questions"]
    }
    if len(review) != 180 or len({r["review_id"] for r in review}) != 180:
        raise ValueError("Missing or repeated reviews")
    by_q, errors, claims, blocked, statuses, reviewers = (
        defaultdict(list),
        Counter(),
        Counter(),
        Counter(),
        Counter(),
        set(),
    )
    for r in review:
        key = mapping[r["review_id"]]
        raw = originals[key["filename"]]
        if (
            sha256_file(generation / key["filename"]) != key["sha256"]
            or r["question_id"] != raw["question_id"]
            or r["answer"] != raw["answer"]
        ):
            raise ValueError("Review no longer matches original")
        q = questions[r["question_id"]]
        expected = {p["point_id"] for p in q["answer_points"]}
        if (
            not r["reviewer_id"]
            or r["reviewer_kind"] not in {"ai_assistant", "human"}
            or not isinstance(r["point_correct"], dict)
            or set(r["point_correct"]) != expected
            or any(
                type(v) is not int or v not in (0, 1)
                for v in r["point_correct"].values()
            )
            or not isinstance(r["point_reasons"], dict)
            or set(r["point_reasons"]) != expected
            or not all(r["point_reasons"].values())
            or not isinstance(r["major_errors"], list)
            or not isinstance(r["claims"], list)
        ):
            raise ValueError("Incomplete identified scientific review")
        arm, status = raw["arm"], raw["result"]["status"]
        reviewers.add((r["reviewer_id"], r["reviewer_kind"]))
        strict = (
            sum(r["point_correct"].values()) / len(expected)
            if status == "success"
            else 0
        )
        penalized = min(strict, 0.5) if r["major_errors"] else strict
        guard_block = (raw.get("answer_validation") or {}).get("status") == "blocked"
        delivered = 0 if guard_block else penalized
        by_q[(arm, q["article_group"], q["question_id"])].append(
            (strict, penalized, delivered)
        )
        errors[arm] += bool(r["major_errors"])
        blocked[arm] += guard_block
        statuses[(arm, status)] += 1
        for claim in r["claims"]:
            if (
                not all(claim.get(k) for k in ["text", "reason"])
                or claim.get("support_label")
                not in {
                    "supported",
                    "partial",
                    "unsupported",
                    "unverifiable",
                    "uncited",
                }
                or not isinstance(claim.get("citation_markers"), list)
                or not isinstance(claim.get("source_refs"), list)
            ):
                raise ValueError("Invalid atomic claim review")
            has_citation = bool(claim["citation_markers"])
            if (claim["support_label"] == "uncited") == has_citation:
                raise ValueError("Citation presence and support label disagree")
            claims[(arm, "all")] += 1
            claims[(arm, "cited")] += has_citation
            claims[(arm, "supported")] += claim["support_label"] == "supported"
    successful = defaultdict(list)
    for r in review:
        raw = originals[mapping[r["review_id"]]["filename"]]
        if raw["result"]["status"] == "success":
            score = sum(r["point_correct"].values()) / len(r["point_correct"])
            score = min(score, 0.5) if r["major_errors"] else score
            successful[
                (
                    raw["arm"],
                    questions[r["question_id"]]["article_group"],
                    r["question_id"],
                )
            ].append(score)
    successful_articles = defaultdict(list)
    for (arm, group, _), values in successful.items():
        successful_articles[(arm, group)].append(float(np.mean(values)))
    grouped = defaultdict(list)
    for (arm, group, _), repetitions in by_q.items():
        if len(repetitions) != 3:
            raise ValueError("Three repetitions required per question/arm")
        grouped[(arm, group)].append(np.mean(repetitions, axis=0))
    article_scores = {k: np.mean(v, axis=0) for k, v in grouped.items()}
    groups = sorted({q["article_group"] for q in questions.values()})
    arms = {}
    for arm in ARMS:
        scores = np.mean([article_scores[(arm, g)] for g in groups], axis=0)
        arms[arm] = {
            "strict_point_score": float(scores[0]),
            "penalized_point_score": float(scores[1]),
            "delivered_score": float(scores[2]),
            "major_error_rate": errors[arm] / 90,
            "guard_block_rate": blocked[arm] / 90,
            "statuses": {s: n for (a, s), n in statuses.items() if a == arm},
            "successful_only_penalized_score": float(
                np.mean(
                    [
                        np.mean(v)
                        for (a, _), v in successful_articles.items()
                        if a == arm
                    ]
                )
            )
            if any(a == arm for a, _ in successful_articles)
            else None,
            "successful_only_article_groups": sum(
                a == arm for a, _ in successful_articles
            ),
            "atomic_factual_claims": claims[(arm, "all")],
            "atomic_supported_claims": claims[(arm, "supported")],
            "atomic_cited_claims": claims[(arm, "cited")],
            "citation_support_rate": claims[(arm, "supported")] / claims[(arm, "cited")]
            if arm == "rag_r01" and claims[(arm, "cited")]
            else None,
            "factual_citation_coverage": claims[(arm, "cited")] / claims[(arm, "all")]
            if arm == "rag_r01" and claims[(arm, "all")]
            else None,
        }
    comparisons = {
        name: paired_bootstrap(
            [
                article_scores[("rag_r01", g)][i] - article_scores[("direct", g)][i]
                for g in groups
            ]
        )
        for i, name in enumerate(
            ["strict_point_score", "penalized_point_score", "delivered_score"]
        )
    }
    result = {
        "schema": "chemqa-p3-results-v1",
        "status": "reviewed_exploratory",
        "reviewers": sorted(reviewers),
        "independent_blind_review": False,
        "questions": 30,
        "article_groups": 20,
        "responses": 180,
        "arms": arms,
        "paired_article_bootstrap": comparisons,
        "review_sha256": sha256_file(directory / "review.json"),
        "protocol_sha256": sha256_file(PROTOCOL),
        "limitations": [
            "Article-specific abstract questions, not general QA accuracy.",
            "Assistant-created labels and non-independent review can bias results.",
            "Different evidence prompts compare whole configurations, not pure retrieval causality.",
        ],
    }
    write_json(ROOT / "docs/P3_RESULTS.json", result)
    print("Exploratory results saved; no automatic CV edit or default switch")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "mode", choices=["freeze", "preview", "verify", "execute", "review", "report"]
    )
    parser.add_argument("--directory", type=Path)
    parser.add_argument("--approved-preview-sha256")
    args = parser.parse_args()
    if args.mode == "freeze":
        freeze()
    elif args.mode == "preview":
        preview()
    elif args.directory is None:
        parser.error("This mode needs --directory")
    elif args.mode == "verify":
        verify_preview(args.directory.resolve())
        print("60 frozen inputs replayed without ranking or API")
    elif args.mode == "execute":
        if not args.approved_preview_sha256:
            parser.error("execute requires human approval of exact preview hash")
        execute(args.directory.resolve(), args.approved_preview_sha256)
    elif args.mode == "review":
        create_review(args.directory.resolve())
    else:
        report(args.directory.resolve())


if __name__ == "__main__":
    main()
