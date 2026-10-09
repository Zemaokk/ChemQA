<a id="readme-top"></a>

<div align="center">
  <h1>ChemQA</h1>
  <p>Ask questions of electrochemistry papers. Follow the answer back to the source.</p>
  <p>
    <a href="docs/README.md"><strong>Documentation</strong></a>
    &middot;
    <a href="docs/tutorials/first-question.md">Get started</a>
    &middot;
    <a href="docs/explanation/evaluation-results.md">Evaluation results</a>
    &middot;
    <a href="CHANGELOG.md">Changelog</a>
  </p>
</div>

ChemQA is a command-line research tool for question answering over a local collection of organic electrocatalysis papers. It extracts PDF text, retrieves passages, and sends selected evidence to a Chat Completions-compatible model. Saved answers retain the actual prompt, document identities, physical PDF pages, source spans, and citation mappings.

The useful part is being able to inspect how an answer was produced. Retrieval, resolved citations, and answer checks each provide a different kind of evidence; none establishes scientific correctness on its own.

## About the project

- Local PDF indexing with tokenizer-aware chunking and validated, separate candidate indexes.
- Stable document/chunk identities and exact extracted-text source locations.
- MiniLM/JSON compatibility retrieval, plus explicit Qwen hybrid/reranking candidates.
- Isolated answer and failure artifacts with prompt, evidence, API status, and provenance.
- Conservative answer checks that preserve rejected output as diagnostics.

Built with Python 3.12, uv, PyMuPDF, Sentence Transformers, NumPy, SQLite, and HTTP generation clients. Matplotlib and Seaborn provide local similarity plots. ChemQA uses pretrained models. Its interface is a CLI; some console messages and frozen protocol inputs are in Chinese.

## Getting started

You need Python 3.12 and uv, PDFs you are permitted to use, model access for the first download, and a compatible generation-provider key.

```sh
uv sync --locked
uv run --locked python main.py --help
```

**The source checkout does not include papers, indexes, or model weights.** Follow [your first literature question](docs/tutorials/first-question.md) to configure the provider, build an index, ask a question, and inspect its evidence. Generation sends selected excerpts to your provider and may incur charges.

Frozen profiles bind specific local experiment assets and are not fresh-install presets. If you have those assets, use the [runtime verification and rollback guide](docs/how-to/frozen-runtime.md).

## Documentation

| Purpose | Entry point |
| --- | --- |
| Learn the complete workflow | [Tutorial](docs/tutorials/first-question.md) |
| Configure, build, verify, inspect, or troubleshoot | [How-to guides](docs/how-to/README.md) |
| Look up CLI flags, settings, artifact fields, and metrics | [Reference](docs/reference/README.md) |
| Understand architecture, reliability, and measured results | [Explanation](docs/explanation/README.md) |
| Understand design choices | [Architecture decision records](docs/decisions/README.md) |
| Find frozen experimental evidence | [Record catalog](docs/reference/experiment-records.md) |
| See current priorities | [Project status](docs/explanation/project-status.md) |

## Evaluation and limits

The recorded local corpus has 181 PDFs with 180 byte identities. The compatibility index contains 26,025 chunks; the Qwen candidate contains 6,960. Different chunk sizes make these counts unsuitable as quality scores.

Q10-B compared five configurations on six reserved questions with three repetitions. Required-point coverage was high for the Qwen candidates, but additional equations and experimental conditions could still be wrong. The study did not establish a general winner or compare legacy MiniLM generation under the same conditions.

P3 added 30 questions from 20 article groups and 180 generations. Raw necessary-point scores were 3.33% for direct generation and 96.67% for R01 RAG. Publication checks rejected 78/90 RAG responses; delivered scores were 3.33% and 9.17%, with a paired difference interval spanning zero. These are exploratory article-specific scores, not general answer accuracy. The default remains unchanged.

PDF signs and charges can be lost during extraction. Citation mapping cannot establish claim support, and lexical answer checks can miss errors or reject valid responses. Read [the full results and limitations](docs/explanation/evaluation-results.md) before interpreting the numbers.

## Development and sharing

See [CONTRIBUTING](CONTRIBUTING.md) for checks and change conventions, [CHANGELOG](CHANGELOG.md) for notable changes, and the [file policy](docs/reference/repository-policy.md) for source-control boundaries.

No project license file is currently present. The development history contains old credentials recorded as revoked and has not been rewritten. Use the documented [source-snapshot workflow](docs/how-to/share-source.md) and review excerpts and local paths before sharing. Papers, models, indexes, generated runs, and the previous documentation archive remain local assets.

## Acknowledgments

README presentation adapted from [Best-README-Template](https://github.com/othneildrew/Best-README-Template). Documentation uses [Diátaxis](https://diataxis.fr/), [Architecture Decision Records](https://github.com/architecture-decision-record/architecture-decision-record), and [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

<p align="right"><a href="#readme-top">Back to top</a></p>
