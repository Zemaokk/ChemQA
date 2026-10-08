"""Pinned Qwen reranking with full-template budgets and checked actual token IDs."""

import hashlib
import re

import numpy as np


def validate_profile(profile):
    if (
        profile.get("schema") != "chemqa-reranker-profile-v1"
        or not isinstance(profile.get("model"), str)
        or not profile["model"]
        or not re.fullmatch("[0-9a-f]{40}", profile.get("revision", ""))
        or not isinstance(profile.get("instruction"), str)
        or not profile["instruction"]
        or type(profile.get("max_sequence_tokens")) is not int
        or profile["max_sequence_tokens"] <= 0
        or type(profile.get("batch_size")) is not int
        or profile["batch_size"] <= 0
        or profile.get("precision_policy") != "mps-fp16-cpu-fp32-v1"
        or profile.get("score_kind") != "yes_minus_no_logit"
        or profile.get("candidate_window") != 50
        or profile.get("tie_break") != "original_candidate_rank"
    ):
        raise ValueError("Invalid or unpinned reranker profile")


class QwenReranker:
    def __init__(self, profile, *, device="auto", model=None):
        validate_profile(profile)
        self.profile = dict(profile)
        if model is None:
            import torch
            from sentence_transformers import CrossEncoder

            if device == "auto":
                device = "mps" if torch.backends.mps.is_available() else "cpu"
            if device not in {"cpu", "mps"}:
                raise ValueError("Unsupported reranker device")
            model = CrossEncoder(
                profile["model"],
                revision=profile["revision"],
                device=device,
                local_files_only=True,
                trust_remote_code=False,
                model_kwargs={
                    "dtype": torch.float16 if device == "mps" else torch.float32,
                    "attn_implementation": "sdpa",
                },
            )
        self.model = model
        if self.model.max_seq_length < profile["max_sequence_tokens"]:
            raise ValueError("Reranker model cannot support requested budget")
        self.model.max_seq_length = profile["max_sequence_tokens"]
        self.tokenizer = model.tokenizer
        self.tokenizer.padding_side = "left"
        self.template_sha256 = hashlib.sha256(
            self.tokenizer.chat_template.encode()
        ).hexdigest()
        self.model.eval()

    def render(self, query, document):
        return self.tokenizer.apply_chat_template(
            [
                {"role": "system", "content": self.profile["instruction"]},
                {"role": "query", "content": query},
                {"role": "document", "content": document},
            ],
            tokenize=False,
            add_generation_prompt=False,
        )

    def prepare(self, pairs):
        texts = [self.render(q, d) for q, d in pairs]
        expected = self.tokenizer(
            texts, add_special_tokens=False, truncation=False, padding=False
        )["input_ids"]
        if any(len(ids) > self.profile["max_sequence_tokens"] for ids in expected):
            raise ValueError(
                "Full reranker template exceeds budget; truncation is forbidden"
            )
        features = self.model.preprocess(
            inputs=pairs, prompt=self.profile["instruction"]
        )
        actual = features["input_ids"].tolist()
        masks = features["attention_mask"].tolist()
        for row, mask, ids in zip(actual, masks, expected, strict=True):
            if [token for token, used in zip(row, mask, strict=True) if used] != ids:
                raise ValueError(
                    "Actual reranker tokens truncate or alter the complete template"
                )
        return features, [len(ids) for ids in expected]

    def score(self, query, hits):
        import torch

        if len(hits) > self.profile["candidate_window"]:
            raise ValueError("Cannot expand the frozen reranker candidate window")
        if len({h["document"]["chunk_id"] for h in hits}) != len(hits):
            raise ValueError("Duplicate reranker candidate identities")
        scores = []
        counts = []
        for start in range(0, len(hits), self.profile["batch_size"]):
            batch = hits[start : start + self.profile["batch_size"]]
            features, n = self.prepare(
                [(query, hit["document"]["text"]) for hit in batch]
            )
            features = {
                k: v.to(self.model.device) if torch.is_tensor(v) else v
                for k, v in features.items()
            }
            with torch.inference_mode():
                output = (
                    self.model(features)["scores"]
                    .detach()
                    .float()
                    .cpu()
                    .numpy()
                    .reshape(-1)
                )
            if output.shape != (len(batch),) or not np.isfinite(output).all():
                raise ValueError("Reranker produced invalid relevance logits")
            scores.extend(output.tolist())
            counts.extend(n)
            if str(self.model.device).startswith("mps"):
                torch.mps.empty_cache()
                if torch.mps.driver_allocated_memory() > 6 * 1024**3:
                    raise RuntimeError(
                        "Reranker exceeds MPS memory guard; rerun explicitly on CPU"
                    )
        return np.asarray(scores, dtype=np.float32), counts

    def rerank(self, query, hits):
        scores, counts = self.score(query, hits)
        order = np.argsort(-scores, kind="stable")
        return [
            {
                **hits[int(i)],
                "score": float(scores[i]),
                "score_kind": "reranker_logit_difference",
                "rerank_input_tokens": counts[int(i)],
                "candidate_rank": int(i) + 1,
                "retrieval_score": hits[int(i)]["score"],
                "retrieval_score_kind": hits[int(i)].get("score_kind", "rrf"),
            }
            for i in order
        ]

    def manifest(self):
        return {
            **self.profile,
            "chat_template_sha256": self.template_sha256,
            "full_template_token_budget": True,
        }
