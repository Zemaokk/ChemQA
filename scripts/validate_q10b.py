"""Freeze holdout inputs before generation; audit structural citations separately."""

import argparse
import json
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace

from config.settings import BASE_DIR, settings
from scripts.validate_q065g import load_inputs
from src.api_integration.api_handler import DeepSeekAPIHandler
from src.api_integration.prompt_builder import prepare_prompt
from src.api_integration.result import GenerationResult
from src.evaluation.citations import citation_statistics
from src.evaluation.comparison import summarize_results
from src.evaluation.dataset import validate_dataset
from src.evaluation.metrics import (
    aggregate_metrics,
    manual_review_template,
    retrieval_metrics,
)
from src.knowledge_base.embedding import CandidateEncoder, profile_from_file
from src.knowledge_base.hybrid_search import HybridSearch
from src.knowledge_base.reranker import QwenReranker
from src.qa_system.context_selection import select_context
from src.qa_system.evidence_policy import NO_EVIDENCE_ANSWER
from src.utils.artifacts import ArtifactRun, sha256_file, write_json

ROOT = Path(BASE_DIR)
PROTOCOL = ROOT / "config/q10b_protocol.json"
DATASET = ROOT / "evaluation/q10b"


def read(path):
    return json.loads(Path(path).read_text())


def check_protocol():
    p = read(PROTOCOL)
    if (
        p["dataset_manifest_sha256"] != sha256_file(DATASET / "manifest.json")
        or p["domain"] != settings.DOMAIN
        or p["repetitions"] != 3
        or p["max_attempts"] != 1
        or p["request_cap"] != 90
    ):
        raise ValueError("Frozen protocol/domain/dataset changed")
    for name, checksum in p["fixed_files_sha256"].items():
        if sha256_file(ROOT / name) != checksum:
            raise ValueError("Frozen component changed: " + name)
    for key, location in [
        ("source_H_run_sha256", Path(p["source_H_profile"]).parent),
        ("source_F_run_sha256", Path(p["source_F_directory"])),
    ]:
        if sha256_file(location / "run.json") != p[key]:
            raise ValueError("Frozen candidate changed")
    return p


def preview(device):
    p = check_protocol()
    _, _, questions, _ = validate_dataset(DATASET)
    reserve = questions["reserve"]
    # Mark holdout consumption BEFORE any new encoding/ranking; never tune/repeat.
    marker = ROOT / "output/Q10B_RESERVE_CONSUMED.json"
    marker.parent.mkdir(exist_ok=True)
    with marker.open("x") as handle:
        json.dump(
            {
                "protocol_sha256": sha256_file(PROTOCOL),
                "status": "started",
                "warning": "Reserve retrieval is now consumed; do not tune using its results.",
            },
            handle,
        )
    store, _, _, _, _ = load_inputs()
    try:
        ep, _ = profile_from_file(ROOT / "config/q065e_embedding.json")
        encoder = CandidateEncoder(ep, device=device)
        vectors = encoder.encode([q["question"] for q in reserve], kind="query")
        mapping = {q["question"]: v for q, v in zip(reserve, vectors, strict=True)}
        del encoder
        store.encoder = SimpleNamespace(encode=lambda text, *, kind: mapping[text])
        hp = read(p["source_H_profile"])
        if not hp["enabled"]:
            raise ValueError("This frozen campaign requires adopted H reranker")
        engine = HybridSearch.from_profile(store, hp["retrieval_profile"])
        reranker = QwenReranker(hp["model_profile"], device=device)
        if reranker.template_sha256 != hp["model_profile"]["chat_template_sha256"]:
            raise ValueError("H tokenizer template changed")
        records = []
        docs = set()
        for q in reserve:
            routes = engine.routes(q["question"], query_vector=mapping[q["question"]])
            ranked = reranker.rerank(q["question"], routes["hybrid"])
            for arm in p["arms"]:
                if arm == "direct":
                    hits = []
                    selection = select_context(
                        q["question"],
                        [],
                        p["common_context_policy"],
                        p["request_body"],
                        template=p["direct_prompt_template"],
                    )
                else:
                    hits = routes[arm] if arm in {"dense", "bm25"} else ranked
                    policy = (
                        p["diverse_context_policy"]
                        if arm.endswith("_diverse")
                        else p["common_context_policy"]
                    )
                    selection = select_context(
                        q["question"], hits, policy, p["request_body"]
                    )
                chunks = selection.prepared.chunks
                docs.update(c["doc_id"] for c in chunks)
                records.append(
                    {
                        "question_id": q["question_id"],
                        "arm": arm,
                        "question": q["question"],
                        "generation_input": selection.prepared.record(),
                        "evidence": chunks,
                        "selection": selection.audit,
                        "retrieval_metrics": retrieval_metrics(
                            q, [{"document": c} for c in chunks]
                        )
                        if arm != "direct"
                        else None,
                    }
                )
            print(q["question_id"] + ": frozen 5 arms", flush=True)
        with ArtifactRun("q10b_previews") as artifact:
            write_json(artifact.path / "requests.json", records)
            write_json(
                artifact.path / "manual_review.json",
                {
                    "status": "not_scored",
                    "arms": {a: manual_review_template(reserve) for a in p["arms"]},
                    "repetitions": 3,
                },
            )
            target = artifact.publish(
                "ready",
                {
                    "files": {
                        n: sha256_file(artifact.path / n)
                        for n in ["requests.json", "manual_review.json"]
                    },
                    "protocol_sha256": sha256_file(PROTOCOL),
                    "dataset_manifest_sha256": sha256_file(DATASET / "manifest.json"),
                    "source_H_run_sha256": p["source_H_run_sha256"],
                },
            )
        write_json(
            marker,
            {
                "status": "preview_ready_generation_not_sent",
                "protocol_sha256": sha256_file(PROTOCOL),
                "artifact_directory": str(target),
                "reserve_retrieval_consumed": True,
            },
        )
        scope = {
            "schema": "chemqa-q10b-send-scope-v1",
            "status": "awaiting_user_authorization",
            "artifact_directory": str(target),
            "preview_run_sha256": sha256_file(target / "run.json"),
            "unique_inputs": len(records),
            "queries": len(reserve),
            "repetitions": 3,
            "maximum_requests": len(records) * 3,
            "maximum_output_tokens": len(records) * 3 * p["request_body"]["max_tokens"],
            "unique_pdf_count": len(docs),
            "generation_requests": 0,
            "human_scientific_review": "pending",
            "exact_provider_input_tokens": None,
            "price_or_total_cost": None,
            "endpoint": "https://llmapi.paratera.com/v1/chat/completions",
        }
        write_json(ROOT / "docs/Q10B_PREVIEW.json", scope)
        lines = [
            "# Q10-B 本地请求范围",
            "",
            "状态：本地预览完成，尚未授权或发送。",
            "",
            f"目录：`{target}`。",
            f"run.json SHA-256：`{scope['preview_run_sha256']}`。",
            "",
            f"固定6个预留问题、5个方案，每个输入3次独立请求，共最多90次；每次最多4096输出 tokens，总计最多368,640输出 tokens。检索输入涉及 {len(docs)} 份 PDF 的片段，不发送整份 PDF、标准答案、评分点或 must_not_claim。Direct 仅发送问题与指导文字。",
            "",
            "目的地：https://llmapi.paratera.com/v1/chat/completions。可能计费，价格和精确输入 token 数未知，不声称费用为0。",
            "",
            "预留检索已经在固定协议下使用；后续不得用结果调参后仍称独立验收。标签与科学评分待人工复核，本次授权不代表评分已完成。",
            "",
            "| 问题 | 方案 | 片段数 | 本地输入字节估算 | payload SHA-256 |",
            "| --- | --- | ---: | ---: | --- |",
        ]
        for r in records:
            b = r["generation_input"]["request_budget"]
            lines.append(
                f"| {r['question_id']} | {r['arm']} | {len(r['evidence'])} | {b['input_estimate']} | `{b['payload_sha256']}` |"
            )
        (ROOT / "docs/Q10B_SEND_SCOPE.md").write_text("\n".join(lines) + "\n")
        print(json.dumps(scope))
    finally:
        store.storage.close()


def audit_baseline():
    """Recompute old answers from their own exact evidence; never reuse new contexts."""
    from scripts.validate_q065b import load_inputs as generation_inputs

    baseline = read(ROOT / "docs/Q06_5B_BASELINE.json")
    directory = Path(baseline["artifact_directory"])
    _, _, _, inputs = generation_inputs(ROOT / "docs/Q10A_BASELINE.json")
    records = []
    for question, prepared in inputs:
        path = directory / (question["question_id"] + ".json")
        row = read(path)
        if prepared.record() != {
            k: v for k, v in row["generation_input"].items() if k != "prompt_sent"
        }:
            raise ValueError("Historical generation evidence differs from snapshot")
        stats = (
            citation_statistics(row["answer"], prepared.chunks)
            if row["result"]["status"] == "success"
            else None
        )
        records.append(
            {
                "question_id": question["question_id"],
                "source_sha256": sha256_file(path),
                "generation_status": row["result"]["status"],
                "citation_statistics": stats,
            }
        )
    write_json(
        ROOT / "docs/Q10B_BASELINE_CITATIONS.json",
        {
            "status": "passed",
            "records": records,
            "generation_requests": 0,
            "scientific_support_scored": False,
            "comparison_note": "Historical single-run dev baseline, not a Q10-B holdout arm.",
        },
    )


def replay(directory):
    protocol = check_protocol()
    run = read(directory / "run.json")
    if (
        run.get("kind") != "q10b_previews"
        or run.get("status") != "ready"
        or run["protocol_sha256"] != sha256_file(PROTOCOL)
    ):
        raise ValueError("Preview protocol changed")
    for name, checksum in run["files"].items():
        if sha256_file(directory / name) != checksum:
            raise ValueError("Frozen preview changed")
    from src.api_integration.prompt_builder import PreparedPrompt
    from src.qa_system.context_selection import verify_budget

    _, _, dataset, _ = validate_dataset(DATASET)
    questions = {q["question_id"]: q["question"] for q in dataset["reserve"]}
    records = read(directory / "requests.json")
    if len(records) != len(questions) * len(protocol["arms"]) or {
        (r["question_id"], r["arm"]) for r in records
    } != {(qid, arm) for qid in questions for arm in protocol["arms"]}:
        raise ValueError("Preview must contain each frozen question/arm exactly once")
    for row in records:
        if row["question"] != questions[row["question_id"]]:
            raise ValueError("Frozen question changed")
        r = row["generation_input"]
        prepared = PreparedPrompt(
            question=row["question"],
            text=r["prompt"],
            serialized_context=r["serialized_context"],
            evidence_json=json.dumps(row["evidence"], ensure_ascii=False),
            template_sha256=r["template_sha256"],
            domain=r["domain"],
            budget_json=json.dumps(r["request_budget"], ensure_ascii=False),
        )
        verify_budget(prepared, read(PROTOCOL)["request_body"])
        policy = protocol[
            "diverse_context_policy"
            if row["arm"].endswith("_diverse")
            else "common_context_policy"
        ]
        if prepared.budget["policy"] != policy:
            raise ValueError("Frozen context policy changed")
        expected = (
            prepare_prompt(
                row["question"],
                row["evidence"],
                template=read(PROTOCOL)["direct_prompt_template"],
            )
            if row["arm"] == "direct"
            else prepare_prompt(row["question"], row["evidence"])
        )
        if (
            expected.text != prepared.text
            or expected.serialized_context != prepared.serialized_context
        ):
            raise ValueError("Prompt/context replay changed")
    write_json(
        ROOT / "docs/Q10B_REPLAY.json",
        {
            "status": "passed",
            "frozen_requests_verified": 30,
            "generation_requests": 0,
            "reserve_reranking_repeated": False,
        },
    )


@contextmanager
def durable_campaign(approved_sha256):
    with ArtifactRun("q10b_generation") as artifact:
        try:
            yield artifact
        except BaseException:
            artifact.publish(
                "interrupted",
                {
                    "preview_run_sha256": approved_sha256,
                    "files": {
                        p.name: sha256_file(p) for p in artifact.path.glob("*.json")
                    },
                    "resume_policy": "No automatic resume or duplicate requests; inspect stored attempts first.",
                },
            )
            raise


def execute(directory, approved_sha256):
    """Call only after human authorization of the exact preview and destination."""
    from src.api_integration.prompt_builder import PreparedPrompt

    replay(directory)
    if approved_sha256 != sha256_file(directory / "run.json"):
        raise ValueError("Approved preview hash differs from actual preview")
    protocol = check_protocol()
    handler = DeepSeekAPIHandler()
    handler.config["max_attempts"] = 1
    if (
        handler.config["base_url"].rstrip("/") != "https://llmapi.paratera.com/v1"
        or handler.request_parameters()["body"] != protocol["request_body"]
    ):
        raise ValueError("Active generation destination/parameters differ from preview")
    marker = ROOT / "output/Q10B_GENERATION_STARTED.json"
    with marker.open("x") as handle:
        json.dump({"preview_run_sha256": approved_sha256, "status": "started"}, handle)
    _, _, dataset, _ = validate_dataset(DATASET)
    questions = {q["question_id"]: q for q in dataset["reserve"]}
    summaries, reviews = [], []
    with durable_campaign(approved_sha256) as artifact:
        for repetition in range(1, protocol["repetitions"] + 1):
            for row in read(directory / "requests.json"):
                record = row["generation_input"]
                prepared = PreparedPrompt(
                    question=row["question"],
                    text=record["prompt"],
                    serialized_context=record["serialized_context"],
                    evidence_json=json.dumps(row["evidence"], ensure_ascii=False),
                    template_sha256=record["template_sha256"],
                    domain=record["domain"],
                    budget_json=json.dumps(
                        record["request_budget"], ensure_ascii=False
                    ),
                )
                # Direct is intentionally a no-retrieval baseline. RAG retains Q06 gate.
                result = (
                    GenerationResult(status="no_evidence", content=NO_EVIDENCE_ANSWER)
                    if row["arm"] != "direct" and not prepared.chunks
                    else handler.generate_result(
                        prepared.text, max_attempts=1, prepared=prepared
                    )
                )
                name = f"{row['question_id']}-{row['arm']}-r{repetition}.json"
                statistics = (
                    citation_statistics(result.content, prepared.chunks)
                    if result.status == "success" and row["arm"] != "direct"
                    else None
                )
                write_json(
                    artifact.path / name,
                    {
                        "question_id": row["question_id"],
                        "arm": row["arm"],
                        "repetition": repetition,
                        "generation_input": {
                            **record,
                            "prompt_sent": result.request_sent,
                        },
                        "evidence": prepared.chunks,
                        "result": result.record(),
                        "answer": result.content,
                        "citation_statistics": statistics,
                        "scientific_quality_scores": None,
                        "cost": None,
                    },
                )
                summaries.append(
                    {
                        "file": name,
                        "question_id": row["question_id"],
                        "arm": row["arm"],
                        "repetition": repetition,
                        "status": result.status,
                        "request_sent": result.request_sent,
                        "usage": result.usage,
                        "elapsed_seconds": result.elapsed_seconds,
                        "cost": None,
                        "retrieval_elapsed_seconds": None,
                    }
                )
                review = manual_review_template([questions[row["question_id"]]])
                review["questions"][0]["answer_run"] = name
                reviews.append(
                    {
                        "file": name,
                        "arm": row["arm"],
                        "repetition": repetition,
                        "review": review,
                    }
                )
                print(name + ": " + result.status, flush=True)
                if not result.request_sent and result.status == "failed":
                    raise ValueError(
                        "Generation configuration failed; campaign stopped"
                    )
        write_json(artifact.path / "manual_review.json", reviews)
        target = artifact.publish(
            "review_pending",
            {
                "preview_run_sha256": approved_sha256,
                "protocol_sha256": sha256_file(PROTOCOL),
                "files": {p.name: sha256_file(p) for p in artifact.path.glob("*.json")},
            },
        )
    write_json(
        ROOT / "docs/Q10B_GENERATION.json",
        {
            "status": "human_review_pending",
            "artifact_directory": str(target),
            "generation_requests": sum(r["request_sent"] for r in summaries),
            "results": summaries,
            "scientific_quality_scores": None,
            "cost": None,
            "production_default_switched": False,
        },
    )


def report(directory):
    protocol = check_protocol()
    scope = read(ROOT / "docs/Q10B_PREVIEW.json")
    preview_directory = Path(scope["artifact_directory"])
    if sha256_file(preview_directory / "run.json") != scope["preview_run_sha256"]:
        raise ValueError("Approved preview changed")
    preview_run = read(preview_directory / "run.json")
    for name, checksum in preview_run["files"].items():
        if sha256_file(preview_directory / name) != checksum:
            raise ValueError("Approved input file changed")
    preview_rows = read(preview_directory / "requests.json")
    approved = {(r["question_id"], r["arm"]): r for r in preview_rows}
    run = read(directory / "run.json")
    if (
        run.get("kind") != "q10b_generation"
        or run.get("status") != "review_pending"
        or run["protocol_sha256"] != sha256_file(PROTOCOL)
        or run["preview_run_sha256"]
        != read(ROOT / "docs/Q10B_PREVIEW.json")["preview_run_sha256"]
    ):
        raise ValueError("Generation run differs from approved preview/protocol")
    for name, checksum in run["files"].items():
        if sha256_file(directory / name) != checksum:
            raise ValueError("Generation record changed")
    rows = [
        read(directory / name) for name in run["files"] if name != "manual_review.json"
    ]
    _, _, dataset, _ = validate_dataset(DATASET)
    expected = {
        (q["question_id"], arm, repetition)
        for q in dataset["reserve"]
        for arm in protocol["arms"]
        for repetition in range(1, 4)
    }
    if (
        len(rows) != 90
        or {(r["question_id"], r["arm"], r["repetition"]) for r in rows} != expected
    ):
        raise ValueError("Campaign does not contain exactly the frozen 90 attempts")
    for row in rows:
        source = approved[(row["question_id"], row["arm"])]
        if {
            k: v for k, v in row["generation_input"].items() if k != "prompt_sent"
        } != source["generation_input"] or row["evidence"] != source["evidence"]:
            raise ValueError("Actual generation inputs differ from approved preview")
        result = row["result"]
        if result["request_sent"] and (
            result["attempts"] != 1
            or result["request_parameters"]["body"] != protocol["request_body"]
        ):
            raise ValueError("Generation attempt/body differs from protocol")
        if (
            result["status"] == "success"
            and row["arm"] != "direct"
            and citation_statistics(row["answer"], row["evidence"])
            != row["citation_statistics"]
        ):
            raise ValueError("Structural citation replay changed")
    summary = summarize_results(rows)
    summary["retrieval_metrics_from_frozen_preview"] = {
        arm: aggregate_metrics(
            [
                {"metrics": r.get("retrieval_metrics")}
                for r in preview_rows
                if r["arm"] == arm
            ],
            "metrics",
        )
        for arm in protocol["arms"]
        if arm != "direct"
    }
    summary["all_90_inputs_match_approved_preview"] = True
    summary.update(
        status="generation_complete_human_review_pending",
        artifact_directory=str(directory),
        generation_requests=sum(r["result"]["request_sent"] for r in rows),
        reserve_questions=6,
        repetitions=3,
    )
    write_json(ROOT / "docs/Q10B_RESULTS.json", summary)
    with ArtifactRun("q10b_review") as review:
        write_json(
            review.path / "answer_review.json", read(directory / "manual_review.json")
        )
        write_json(
            review.path / "annotation_review.json",
            read(ROOT / "docs/Q10B_ANNOTATION_REVIEW.json"),
        )
        lines = [
            "# Q10-B 人工评审包",
            "",
            "AI 标注待研究者核对；以下模型答案未经科学支持验证。不要修改冻结生成文件，编辑本目录的评审 JSON 副本。",
            "",
        ]
        for question in dataset["reserve"]:
            lines += [
                "## " + question["question_id"],
                "",
                question["question"],
                "",
                "### AI 草案参考要点（待核对）",
                "",
            ]
            lines += ["- " + p["text"] for p in question["answer_points"]]
            for anchor in question["evidence"]:
                lines += [
                    "",
                    f"原文 {anchor['doc_id']}，PDF第{anchor['page_number']}页，字符[{anchor['char_start']}, {anchor['char_end']})：",
                    "",
                    "```text",
                    anchor["quote"],
                    "```",
                ]
            for row in sorted(
                (r for r in rows if r["question_id"] == question["question_id"]),
                key=lambda r: (r["arm"], r["repetition"]),
            ):
                name = f"{row['question_id']}-{row['arm']}-r{row['repetition']}.json"
                lines += [
                    "",
                    f"### {row['arm']} / repeat {row['repetition']} / {row['result']['status']}",
                    "",
                    f"[完整输入/证据与结果]({directory / name})",
                    "",
                    row["answer"] or "没有完整答案；失败/截断不得当作已完成的0分回答。",
                ]
        (review.path / "review.md").write_text("\n".join(lines) + "\n")
        target = review.publish(
            "human_review_pending",
            {
                "generation_run_sha256": sha256_file(directory / "run.json"),
                "files": {p.name: sha256_file(p) for p in review.path.iterdir()},
            },
        )
    summary["human_review_directory"] = str(target)
    write_json(ROOT / "docs/Q10B_RESULTS.json", summary)
    print(
        json.dumps(
            {
                "status": summary["status"],
                "generation_requests": summary["generation_requests"],
                "human_review_directory": str(target),
            }
        )
    )


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "mode", choices=["preview", "replay", "audit-baseline", "execute", "report"]
    )
    p.add_argument("--device", choices=["cpu", "mps", "auto"], default="auto")
    p.add_argument("--candidate", type=Path)
    p.add_argument("--approved-preview-sha256")
    a = p.parse_args()
    if a.mode == "preview":
        preview(a.device)
    elif a.mode == "audit-baseline":
        audit_baseline()
    elif a.mode == "execute":
        if a.candidate is None or not a.approved_preview_sha256:
            p.error(
                "execute needs --candidate and --approved-preview-sha256 after human authorization"
            )
        execute(a.candidate, a.approved_preview_sha256)
    elif a.mode == "report":
        if a.candidate is None:
            p.error("report needs --candidate")
        report(a.candidate)
    elif a.candidate:
        replay(a.candidate)
    else:
        p.error("replay needs --candidate")


if __name__ == "__main__":
    main()
