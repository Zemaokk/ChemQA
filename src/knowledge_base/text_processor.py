from bisect import bisect_right

from config.settings import settings
from src.knowledge_base.identity import normalize_chunk
from src.knowledge_base.location import (
    clean_with_offsets,
    locate_chunks,
    locate_intervals,
    unavailable_location,
)
from src.knowledge_base.token_budget import TokenBudget

PROCESSING_VERSION = "whitespace-only-model-tokens-v1"


class TextProcessor:
    def __init__(self, model=None, *, legacy: bool = False):
        self.legacy = legacy
        # These word counts are only used to replay Q01/Q02 historical data.
        self.chunk_size = settings.LEGACY_CHUNK_WORDS
        self.chunk_overlap = settings.LEGACY_CHUNK_OVERLAP_WORDS
        self.token_overlap = settings.CHUNK_OVERLAP_TOKENS
        self.budget = TokenBudget(model) if model is not None else None

    def _budget(self) -> TokenBudget:
        if self.budget is None:
            from src.knowledge_base.vector_store import VectorStore

            self.budget = TokenBudget(VectorStore.__new__(VectorStore)._load_model())
        return self.budget

    def clean_text(self, text: str) -> str:
        """Normalize whitespace; preserve all extracted scientific characters."""
        return clean_with_offsets(text, preserve_symbols=not self.legacy)[0]

    def split_intervals(self, text: str) -> list[tuple[int, int]]:
        if not text:
            return []
        budget = self._budget()
        payload = budget.limit - budget.special_tokens
        if not 0 <= self.token_overlap < payload:
            raise ValueError("Token overlap must be smaller than the content budget")
        tokens = budget.tokenize(text)["offset_mapping"]
        token_ends = [end for _, end in tokens]
        intervals = []
        start = 0
        while start < len(text):
            position = bisect_right(token_ends, start)
            stop = min(position + payload, len(tokens))
            end = len(text) if stop == len(tokens) else tokens[stop - 1][1]
            # Prefer whole words; exceptionally long words are sliced without decoding.
            if end < len(text) and not text[end].isspace():
                boundary = text.rfind(" ", start, end)
                if boundary > start:
                    end = boundary
            end = max(start + 1, end)
            while budget.count(text[start:end]) > budget.limit:
                local = budget.tokenize(text[start:end])["offset_mapping"]
                shortened = local[-1][0]
                end = start + shortened if shortened > 0 else end - 1
                if end <= start:
                    raise ValueError(
                        "One extracted character exceeds the model token budget"
                    )
            while end > start and text[end - 1].isspace():
                end -= 1
            intervals.append((start, end))
            if end == len(text):
                break
            local = budget.tokenize(text[start:end])["offset_mapping"]
            next_start = end
            if self.token_overlap and len(local) > self.token_overlap:
                target = start + local[-self.token_overlap][0]
                boundary = text.rfind(" ", start, target)
                next_start = boundary + 1 if boundary > start else target
            start = max(start + 1, next_start)
            while start < len(text) and text[start].isspace():
                start += 1
        return intervals

    def split_text(self, text: str) -> list[str]:
        if not self.legacy:
            return [text[start:end] for start, end in self.split_intervals(text)]
        if self.chunk_size <= 0 or not 0 <= self.chunk_overlap < self.chunk_size:
            raise ValueError("Invalid legacy word chunk size/overlap")
        words = text.split()
        return [
            " ".join(words[i : i + self.chunk_size])
            for i in range(0, len(words), self.chunk_size - self.chunk_overlap)
        ]

    def add_metadata(self, chunk: str, metadata: dict, chunk_idx: int) -> dict:
        new_meta = metadata.copy()
        new_meta.pop("num_tokens", None)
        new_meta.update({"chunk_index": chunk_idx, "word_count": len(chunk.split())})
        if not self.legacy:
            budget = self._budget()
            budget.check([chunk])
            new_meta.update(
                {
                    "text_processing_version": PROCESSING_VERSION,
                    "embedding_token_count": budget.count(chunk),
                    "embedding_token_limit": budget.limit,
                    "chunk_overlap_target_tokens": self.token_overlap,
                }
            )
        identified = normalize_chunk({"text": chunk, "metadata": new_meta})
        return {
            "text": chunk,
            "metadata": {k: v for k, v in identified.items() if k != "text"},
        }

    def process_document(self, document: dict) -> list[dict]:
        cleaned, offsets = clean_with_offsets(
            document["text"], preserve_symbols=not self.legacy
        )
        if self.legacy:
            locations = locate_chunks(document, self.chunk_size, self.chunk_overlap)
            chunks = self.split_text(cleaned)
            locations = locations or [
                unavailable_location("page_text_not_supplied") for _ in chunks
            ]
        else:
            intervals = self.split_intervals(cleaned)
            chunks = [cleaned[start:end] for start, end in intervals]
            locations = locate_intervals(document, intervals, offsets)
        return [
            self.add_metadata(
                chunk,
                {
                    **document["metadata"],
                    **{
                        k: v
                        for k, v in location.items()
                        if k not in ("text", "chunk_index")
                    },
                },
                i,
            )
            for i, (chunk, location) in enumerate(zip(chunks, locations, strict=True))
        ]
