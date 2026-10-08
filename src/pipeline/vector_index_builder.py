import json
import os
from pathlib import Path

from config.settings import configure_paths, resolve_path, settings
from src.knowledge_base.identity import unique_chunks
from src.knowledge_base.pdf_loader import PDFLoader
from src.knowledge_base.text_processor import TextProcessor
from src.knowledge_base.vector_store import VectorStore
from src.utils.artifacts import ArtifactRun, sha256_file
from src.utils.logger import logger


class VectorIndexBuilder:
    def __init__(self, pdf_dir: str | None = None):
        """
        初始化向量索引构建器

        Args:
            pdf_dir: PDF文件目录，如果为None则使用settings中的默认目录
        """
        if settings.EMBEDDING_PROFILE:
            raise ValueError(
                "Build profile candidates with scripts.validate_q065e build; the legacy builder is unchanged"
            )
        self.pdf_dir = str(resolve_path(pdf_dir or settings.RAW_PAPERS_DIR))
        self.pdf_loader = PDFLoader(self.pdf_dir)
        self.vector_store = VectorStore(load_index=False)
        self.text_processor = TextProcessor(model=self.vector_store.model)

    def process_documents(self) -> list[dict]:
        """处理所有文档并返回处理后的文本块"""
        all_processed_chunks = []
        pdf_files = self.pdf_loader.load_pdfs()
        logger.info(f"共检测到PDF文件：{len(pdf_files)}")

        for number, pdf_path in enumerate(pdf_files, 1):
            results = self.pdf_loader.load_pdf(pdf_path)
            if not results:
                raise ValueError(
                    f"Unable to extract PDF text; rebuild stopped: {pdf_path}"
                )

            for doc in results:
                chunks = self.text_processor.process_document(doc)
                all_processed_chunks.extend(chunks)
            if number % 10 == 0 or number == len(pdf_files):
                logger.info(
                    "已处理 PDF %s/%s；累计片段 %s",
                    number,
                    len(pdf_files),
                    len(all_processed_chunks),
                )

        identified = unique_chunks(all_processed_chunks)
        return [
            {"text": d["text"], "metadata": {k: v for k, v in d.items() if k != "text"}}
            for d in identified
        ]

    def save_processed_chunks(
        self, chunks: list[dict], output_dir: str | None = None
    ) -> str:
        """保存处理后的文本块到JSON文件"""
        if output_dir is None:
            raise ValueError("Use run_pipeline() to publish a validated candidate")
        directory = resolve_path(output_dir)
        if (directory / "run.json").exists():
            raise ValueError("Published candidate indexes are immutable")
        os.makedirs(directory, exist_ok=True)
        processed_file = os.path.join(directory, "processed_chunks.json")

        with open(processed_file, "w", encoding="utf-8") as f:
            json.dump(chunks, f, ensure_ascii=False, indent=2)

        logger.info(f"已保存处理后的文本块到：{processed_file}")
        return processed_file

    def build_index(
        self, chunks: list[dict] | None = None, output_dir: str | None = None
    ) -> None:
        """
        构建或重建向量索引

        Args:
            chunks: 可选的文本块列表，如果为None则重新处理所有文档
        """
        if chunks is None:
            chunks = self.process_documents()

        all_docs = unique_chunks(chunks)
        if not all_docs:
            raise ValueError("No chunks to index; refusing an empty rebuild")
        all_vecs = self.vector_store.encode_texts(
            [doc["text"] for doc in all_docs], batch_size=32, show_progress_bar=True
        )
        save_data = {
            "documents": all_docs,
            "vectors": all_vecs.tolist(),
            "embedding": self.vector_store.budget.manifest(),
        }

        # 确保输出目录存在
        if output_dir is None:
            raise ValueError("Use run_pipeline() to publish a validated candidate")
        directory = resolve_path(output_dir)
        if (directory / "run.json").exists():
            raise ValueError("Published candidate indexes are immutable")
        os.makedirs(directory, exist_ok=True)

        out_path = os.path.join(directory, "vector_index.json")
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(save_data, f, ensure_ascii=False, indent=2)

        logger.info(
            f"向量索引重建完成，文献分块数：{len(all_docs)}，输出文件：{out_path}"
        )

    def run_pipeline(self, destination: str | Path | None = None) -> Path:
        """Validate and publish a new candidate; never replace the active index."""
        from scripts.validate_q03 import validate

        with ArtifactRun("indexes", destination=destination) as run:
            chunks = self.process_documents()
            self.save_processed_chunks(chunks, output_dir=str(run.path))
            self.build_index(chunks, output_dir=str(run.path))
            index = json.loads(
                (run.path / "vector_index.json").read_text(encoding="utf-8")
            )
            report = validate(index, chunks, self.vector_store.model)
            target = run.publish(
                "ready",
                {
                    "raw_papers_dir": self.pdf_dir,
                    "validation": report,
                    "files": {
                        name: sha256_file(run.path / name)
                        for name in ("vector_index.json", "processed_chunks.json")
                    },
                },
            )
        logger.info("Validated candidate index saved to %s", target)
        return target


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Build a validated candidate index without overwriting active data"
    )
    parser.add_argument(
        "--pdf-dir", help="PDF directory (relative to project root or absolute)"
    )
    parser.add_argument("--destination", help="New candidate directory; must not exist")
    parser.add_argument("--output-dir", help="Root for generated candidates")
    args = parser.parse_args()
    configure_paths(output_dir=args.output_dir)
    builder = VectorIndexBuilder(pdf_dir=args.pdf_dir)
    print(builder.run_pipeline(destination=args.destination))


if __name__ == "__main__":
    main()
