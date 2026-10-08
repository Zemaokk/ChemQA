import os
from pathlib import Path

import pymupdf as fitz

from config.settings import settings
from src.knowledge_base.identity import document_id
from src.utils.logger import logger


class PDFLoader:
    def __init__(self, pdf_dir: str | None = None):
        self.pdf_dir = pdf_dir or settings.RAW_PAPERS_DIR

    def load_pdfs(self) -> list[str]:
        """获取所有PDF文件路径"""
        pdf_files = []
        for root, dirs, files in os.walk(self.pdf_dir):
            dirs.sort()
            for file in sorted(files):
                if file.lower().endswith(".pdf"):
                    pdf_files.append(os.path.join(root, file))
        return pdf_files

    def load_pdf(self, pdf_path: str) -> list[dict]:
        """加载单个PDF文件并返回其内容"""
        try:
            if not os.path.exists(pdf_path):
                logger.error(f"PDF file not found: {pdf_path}")
                return []

            pdf_bytes = Path(pdf_path).read_bytes()
            pages = []
            text_parts = []
            cursor = 0
            with fitz.open(stream=pdf_bytes, filetype="pdf") as doc:
                total_pages = len(doc)
                for number, page in enumerate(doc, 1):
                    page_text = page.get_text("text", sort=False)
                    pages.append(
                        {
                            "page_number": number,
                            "char_start": cursor,
                            "char_end": cursor + len(page_text),
                            "text": page_text,
                        }
                    )
                    text_parts.append(page_text)
                    cursor += len(page_text)
            text = "".join(text_parts)

            if not text.strip():
                logger.warning(f"No text content found in {pdf_path}")
                return []

            metadata = {
                "source": pdf_path,
                "doc_id": document_id(pdf_bytes),
                "title": os.path.basename(pdf_path),
                "total_pages": total_pages,
            }

            return [
                {
                    "text": text,
                    "metadata": metadata,
                    "pages": pages,
                    "extraction": {
                        "library": "pymupdf",
                        "version": fitz.VersionBind,
                        "method": "get_text(text, sort=False)",
                    },
                }
            ]

        except Exception:
            logger.exception("Error processing %s", pdf_path)
            return []

    def extract_text(self, pdf_path: str) -> dict[str, str]:
        """提取PDF文本内容和元数据"""
        results = self.load_pdf(pdf_path)
        return results[0] if results else {"text": "", "metadata": {}}
