"""Pack extracted text blocks under a token cap without rewriting source text."""

from bisect import bisect_right
from types import SimpleNamespace

from src.knowledge_base.identity import normalize_chunk
from src.knowledge_base.location import clean_with_offsets, locate_intervals
from src.knowledge_base.text_processor import TextProcessor

PROCESSING_VERSION = "page-block-model-tokens-v1"


class ParagraphProcessor:
    def __init__(
        self, encoder, *, target_tokens=512, overlap_tokens=64, use_blocks=True
    ):
        if not 0 < target_tokens <= encoder.limit:
            raise ValueError("Chunk target exceeds encoder limit")
        self.base = TextProcessor(
            model=SimpleNamespace(
                tokenizer=encoder.tokenizer, max_seq_length=target_tokens
            )
        )
        self.base.token_overlap = overlap_tokens
        if not 0 <= overlap_tokens < target_tokens - self.base.budget.special_tokens:
            raise ValueError("Invalid token overlap")
        self.target = target_tokens
        self.overlap = overlap_tokens
        self.use_blocks = use_blocks

    def split_intervals(self, text, paragraph_ends, page_ends):
        if not text:
            return []
        budget = self.base.budget
        token_ends = [b for _, b in budget.tokenize(text)["offset_mapping"]]
        if not token_ends:
            raise ValueError("Nonempty text produced no tokens")
        payload = self.target - budget.special_tokens
        intervals, start = [], 0
        while start < len(text):
            position = bisect_right(token_ends, start)
            stop = min(position + payload, len(token_ends))
            end = len(text) if stop == len(token_ends) else token_ends[stop - 1]
            next_page = page_ends[bisect_right(page_ends, start)]
            end = min(end, next_page)
            if end < len(text) and not text[end].isspace():
                boundary = text.rfind(" ", start, end)
                if boundary > start:
                    end = boundary
            end = max(start + 1, end)
            while budget.count(text[start:end]) > self.target:
                local = budget.tokenize(text[start:end])["offset_mapping"]
                shortened = local[-1][0]
                end = start + shortened if shortened > 0 else end - 1
                if end <= start:
                    raise ValueError("One extracted character exceeds token budget")
            candidates = paragraph_ends[
                bisect_right(paragraph_ends, start) : bisect_right(paragraph_ends, end)
            ]
            if self.use_blocks and candidates:
                preferred = candidates[-1]
                if budget.count(text[start:preferred]) >= self.target // 2:
                    end = preferred
            while end > start and text[end - 1].isspace():
                end -= 1
            intervals.append((start, end))
            if end == len(text):
                break
            next_start = end
            # Never repeat content across a physical-page boundary.
            if text[end:next_page].strip() and self.overlap:
                local = budget.tokenize(text[start:end])["offset_mapping"]
                if len(local) > self.overlap:
                    target = start + local[-self.overlap][0]
                    boundary = text.rfind(" ", start, target)
                    next_start = boundary + 1 if boundary > start else target
            start = max(start + 1, next_start)
            while start < len(text) and text[start].isspace():
                start += 1
        return intervals

    def process_document(self, document):
        cleaned, offsets = clean_with_offsets(document["text"], preserve_symbols=True)
        if not cleaned:
            return []
        raw_ends = [end for _, end in offsets]
        pages = sorted(
            set(
                [bisect_right(raw_ends, p["char_end"]) for p in document["pages"]]
                + [len(cleaned)]
            )
        )
        boundaries = sorted(
            {bisect_right(raw_ends, end) for end in document.get("paragraph_ends", [])}
        )
        intervals = self.split_intervals(cleaned, boundaries, pages)
        locations = locate_intervals(document, intervals, offsets)
        records = []
        for i, ((start, end), location) in enumerate(
            zip(intervals, locations, strict=True)
        ):
            text = cleaned[start:end]
            if not text or self.base.budget.count(text) > self.target:
                raise ValueError("Invalid empty/oversized chunk")
            record = {
                **document["metadata"],
                **location,
                "text": text,
                "chunk_index": i,
                "text_processing_version": PROCESSING_VERSION,
                "chunking_strategy": "page-block" if self.use_blocks else "page-window",
                "embedding_token_count": self.base.budget.count(text),
                "embedding_token_limit": self.target,
                "chunk_overlap_target_tokens": self.overlap,
                "word_count": len(text.split()),
            }
            records.append(normalize_chunk(record))
        return records
