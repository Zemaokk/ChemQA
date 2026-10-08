"""Explicit query/document encoding for opt-in, revision-pinned candidates."""

import re

import numpy as np

from src.utils.artifacts import sha256_file


def validate_profile(profile):
    if (
        profile.get("schema") != "chemqa-embedding-profile-v1"
        or not re.fullmatch(r"[0-9a-f]{40}", profile.get("revision", ""))
        or not isinstance(profile.get("model"), str)
        or not profile["model"]
        or type(profile.get("dimension")) is not int
        or profile["dimension"] <= 0
        or type(profile.get("max_sequence_tokens")) is not int
        or profile["max_sequence_tokens"] <= 0
        or not isinstance(profile.get("query_prompt"), str)
        or not isinstance(profile.get("document_prompt"), str)
        or profile.get("normalize_embeddings") is not True
        or profile.get("padding_side") != "left"
        or profile.get("precision_policy") != "mps-fp16-cpu-fp32-v1"
    ):
        raise ValueError("Invalid or unpinned embedding profile")


class CandidateEncoder:
    def __init__(self, profile, *, model=None, device="auto"):
        validate_profile(profile)
        self.profile = dict(profile)
        self.limit = profile["max_sequence_tokens"]
        if model is None:
            import torch
            from sentence_transformers import SentenceTransformer

            if device == "auto":
                device = "mps" if torch.backends.mps.is_available() else "cpu"
            if device not in {"cpu", "mps"}:
                raise ValueError("Candidate device must be cpu, mps or auto")
            dtype = torch.float16 if device == "mps" else torch.float32
            model = SentenceTransformer(
                profile["model"],
                revision=profile["revision"],
                device=device,
                local_files_only=True,
                model_kwargs={"dtype": dtype},
                processor_kwargs={"padding_side": "left"},
            )
        self.model = model
        self.tokenizer = model.tokenizer
        if (
            not self.tokenizer.is_fast
            or self.limit > model.max_seq_length
            or model.get_embedding_dimension() != profile["dimension"]
        ):
            raise ValueError("Model does not match profile limits/dimension/tokenizer")
        self.model.max_seq_length = self.limit
        self.tokenizer.padding_side = profile["padding_side"]
        self.special_tokens = self.tokenizer.num_special_tokens_to_add(pair=False)

    def tokenize(self, text):
        return self.tokenizer(
            text,
            add_special_tokens=False,
            truncation=False,
            return_offsets_mapping=True,
            verbose=False,
        )

    def inputs(self, texts, kind):
        if kind not in {"query", "document"}:
            raise ValueError("Unknown embedding input kind")
        return [self.profile[f"{kind}_prompt"] + text for text in texts]

    def count(self, text, kind="document"):
        return len(
            self.tokenizer(
                self.inputs([text], kind)[0],
                add_special_tokens=True,
                truncation=False,
                verbose=False,
            )["input_ids"]
        )

    def check(self, texts, kind="document"):
        counts = [self.count(t, kind) for t in texts]
        if any(c > self.limit for c in counts):
            raise ValueError(
                f"{kind} input exceeds {self.limit} tokens including prompt and special tokens"
            )
        return counts

    def check_actual_inputs(self, texts, kind="document"):
        counts = self.check(texts, kind)
        full = self.inputs(texts, kind)
        expected = self.tokenizer(
            full,
            add_special_tokens=True,
            truncation=False,
            padding=False,
            verbose=False,
        )["input_ids"]
        actual = self.model.preprocess(full)
        for ids, mask, tokens in zip(
            actual["input_ids"].tolist(),
            actual["attention_mask"].tolist(),
            expected,
            strict=True,
        ):
            if [token for token, used in zip(ids, mask, strict=True) if used] != tokens:
                raise ValueError(
                    "Actual encoder inputs truncate or alter untruncated tokens"
                )
        return counts

    def encode(self, texts, *, kind="document", batch_size=8, **kwargs):
        scalar = isinstance(texts, str)
        texts = [texts] if scalar else list(texts)
        if batch_size <= 0:
            raise ValueError("Batch size must be positive")
        if set(kwargs) & {
            "prompt",
            "prompt_name",
            "normalize_embeddings",
            "truncate_dim",
            "precision",
        }:
            raise ValueError("Embedding profile cannot be overridden during encoding")
        for start in range(0, len(texts), batch_size):
            self.check_actual_inputs(texts[start : start + batch_size], kind)
        vectors = np.asarray(
            self.model.encode(
                self.inputs(texts, kind),
                prompt="",
                normalize_embeddings=True,
                batch_size=batch_size,
                **kwargs,
            ),
            dtype=np.float32,
        )
        if (
            vectors.shape != (len(texts), self.profile["dimension"])
            or not np.isfinite(vectors).all()
        ):
            raise ValueError("Invalid candidate embedding matrix")
        norms = np.linalg.norm(vectors, axis=1, keepdims=True)
        if np.any(norms == 0):
            raise ValueError("Candidate produced zero vectors")
        # Canonical float32 normalization also removes fp16 rounding drift.
        vectors = vectors / norms
        return vectors[0] if scalar else vectors

    def manifest(self):
        return {**self.profile, "token_count_includes_prompt_and_special_tokens": True}


def profile_from_file(path):
    import json

    profile = json.loads(path.read_text(encoding="utf-8"))
    validate_profile(profile)
    return profile, sha256_file(path)
