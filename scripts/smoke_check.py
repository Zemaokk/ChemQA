"""Check the Q0 environment without API calls or rebuilding the index.

Run from the project root: uv run --locked python -m scripts.smoke_check
Add --retrieval to load the embedding model and search the existing index.
"""

import argparse
import importlib
import json
from importlib.metadata import version
from pathlib import Path

import numpy as np
import pymupdf

from config.settings import settings
from src.api_integration.api_handler import DeepSeekAPIHandler


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--retrieval", action="store_true")
    args = parser.parse_args()

    for package in (
        "numpy",
        "matplotlib",
        "seaborn",
        "pymupdf",
        "sentence-transformers",
        "requests",
        "python-dotenv",
        "torch",
    ):
        print(f"{package}: {version(package)}")
    for module in (
        "src.knowledge_base.pdf_loader",
        "src.knowledge_base.text_processor",
        "src.knowledge_base.retriever",
        "src.pipeline.vector_index_builder",
        "src.qa_system.expert_system",
        "src.visualization.heatmap",
    ):
        importlib.import_module(module)
    print("Core imports: PASS")

    pdfs = sorted(Path(settings.RAW_PAPERS_DIR).glob("*.pdf"))
    if not pdfs:
        raise RuntimeError("No local PDF found for the read check")
    with pymupdf.open(pdfs[0]) as pdf:
        text = pdf[0].get_text()
        if not text.strip():
            raise RuntimeError("First PDF page has no extractable text")
        print(f"PDF read: PASS ({len(pdf)} pages; first page {len(text)} characters)")

    # Exercise missing-key behavior without using or printing any real key.
    handler = DeepSeekAPIHandler()
    handler.config = dict(handler.config, api_key="")
    try:
        handler.send_request([])
    except ValueError as exc:
        if "DEEPSEEK_API_KEY" not in str(exc):
            raise
        print("Missing API key: PASS (rejected before network request)")
    else:
        raise AssertionError("An empty API key was accepted")

    if args.retrieval:
        index_path = Path(settings.VECTOR_DB_DIR) / "vector_index.json"
        index = json.loads(index_path.read_text(encoding="utf-8"))
        # Refuse legacy indexes which the current loader would rewrite.
        if "documents" not in index or "vectors" not in index:
            raise RuntimeError(
                "Legacy index requires migration; skipped to preserve it"
            )
        vectors = np.asarray(index["vectors"])
        if vectors.ndim != 2 or len(index["documents"]) != len(vectors):
            raise RuntimeError("Index documents and vectors are inconsistent")
        from src.knowledge_base.retriever import Retriever

        retriever = Retriever()
        if (
            retriever.vector_store.model.get_sentence_embedding_dimension()
            != vectors.shape[1]
        ):
            raise RuntimeError("Embedding dimension does not match the existing index")
        results = retriever.search("What is organic electrocatalysis?", top_k=3)
        if len(results) != min(3, len(vectors)):
            raise RuntimeError("Unexpected retrieval result count")
        for result in results:
            if not np.isfinite(result["score"]) or not result["document"]["text"]:
                raise RuntimeError("Invalid retrieval result")
        print(f"Local retrieval: PASS ({len(results)} results; index {vectors.shape})")
        print("This checks execution only; retrieval quality is not evaluated.")


if __name__ == "__main__":
    main()
