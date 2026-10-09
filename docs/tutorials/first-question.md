# Your first literature question

In this exercise you will build a local index from a paper, ask a question, and inspect the saved evidence. Use a text-based PDF you are permitted to process and send excerpts from. Choose a question about a result explicitly stated in that paper.

You need Python 3.12, uv, network access for the first model download, and a compatible generation-provider account. Run the commands from the project root.

## 1. Prepare the environment

```sh
uv sync --locked
uv run --locked python main.py --help
cp .env.example .env
```

If `.env` already exists, keep it and edit it directly. Set your own `DEEPSEEK_API_KEY`, `DEEPSEEK_BASE_URL`, and `DEEPSEEK_MODEL` there. The client appends `/chat/completions` to the base URL. The [provider guide](../how-to/configure-provider.md) has a recorded configuration.

## 2. Add the paper

```sh
mkdir -p data/raw_papers
```

Copy your PDF into that directory. Dependency installation does not supply papers, indexes, or model weights. If the directory already contains other papers, the next step will index those too.

## 3. Build an index

```sh
CHEMQA_EMBEDDING_PROFILE= \
CHEMQA_EMBEDDING_MODEL=sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2 \
CHEMQA_EMBEDDING_REVISION=e8f8c211226b894fcb81acc59f3b34ba3efd5f42 \
uv run --locked python -m src.pipeline.vector_index_builder \
  --pdf-dir data/raw_papers --destination output/indexes/first-paper
```

The builder may download weights. It extracts and embeds the PDFs without calling the generation API, validates the files, and publishes a ready index. Expect `vector_index.json`, `processed_chunks.json`, and `run.json` in the destination. An existing destination is rejected; choose a new name if you repeat the exercise.

## 4. Ask the question

Replace the example question with the result you selected from your paper:

```sh
CHEMQA_EMBEDDING_PROFILE= \
CHEMQA_EMBEDDING_MODEL=sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2 \
CHEMQA_EMBEDDING_REVISION=e8f8c211226b894fcb81acc59f3b34ba3efd5f42 \
uv run --locked python main.py --index-dir output/indexes/first-paper \
  -q "What evidence supports the proposed reaction mechanism?"
```

This step sends the question and retrieved excerpts to your provider and may incur charges. A successful generation prints an answer and the run directory. An empty retrieval returns `no_evidence` locally; a failed request or rejected answer produces diagnostics. Follow [troubleshooting](../how-to/troubleshoot.md) if the exercise stops here.

## 5. Follow a citation

Open `answer.md` and `answer.evidence.json` in the printed `output/qa/<run-id>/` directory. Compare a cited passage with the paper's physical PDF page. Check the units, signs, and experimental conditions yourself. The saved prompt shows the evidence actually supplied to the model.

You have now used the entire pipeline and inspected one answer's provenance. Next, [inspect the evidence in detail](../how-to/inspect-evidence.md) or [build another index](../how-to/build-index.md).

[Documentation home](../README.md)
