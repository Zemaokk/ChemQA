"""Use the encoder's actual tokenizer and effective sequence limit."""

from config.settings import settings


class TokenBudget:
    def __init__(self, model):
        self.tokenizer = model.tokenizer
        self.limit = int(model.max_seq_length)
        self.special_tokens = self.tokenizer.num_special_tokens_to_add(pair=False)
        if not self.tokenizer.is_fast or self.limit <= self.special_tokens:
            raise ValueError(
                "A fast tokenizer and positive content token budget are required"
            )

    def tokenize(self, text: str) -> dict:
        return self.tokenizer(
            text,
            add_special_tokens=False,
            truncation=False,
            return_offsets_mapping=True,
            verbose=False,
        )

    def count(self, text: str) -> int:
        return len(self.tokenize(text)["input_ids"]) + self.special_tokens

    def check(self, texts: list[str]) -> None:
        for i, text in enumerate(texts):
            count = self.count(text)
            if count > self.limit:
                raise ValueError(
                    f"Embedding input {i} has {count} tokens; model limit is {self.limit}. "
                    "Split the document or shorten the query before encoding."
                )

    def manifest(self) -> dict:
        return {
            "model": settings.EMBEDDING_MODEL,
            "revision": settings.EMBEDDING_MODEL_REVISION,
            "max_sequence_tokens": self.limit,
            "special_tokens": self.special_tokens,
            "token_count_includes_special_tokens": True,
        }
