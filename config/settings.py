# 主配置文件

import os
from pathlib import Path
from typing import ClassVar

from dotenv import load_dotenv

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Shell environment takes priority; locate .env independently of the working directory.
load_dotenv(os.path.join(BASE_DIR, ".env"), override=False)


def resolve_path(value: str | Path) -> Path:
    path = Path(value).expanduser()
    return (path if path.is_absolute() else Path(BASE_DIR) / path).resolve()


def path_setting(name: str, default: str | Path) -> str:
    return str(resolve_path(os.getenv(name) or default))


# dotenv/HF cache paths must have the same meaning before and after changing cwd.
if os.getenv("HF_HOME"):
    os.environ["HF_HOME"] = str(resolve_path(os.environ["HF_HOME"]))


class Settings:
    # 数据路径
    RAW_PAPERS_DIR = path_setting("CHEMQA_RAW_PAPERS_DIR", "data/raw_papers")
    VECTOR_DB_DIR = path_setting("CHEMQA_INDEX_DIR", "data/vector_db")
    PROCESSED_DIR = path_setting(
        "CHEMQA_PROCESSED_DIR",
        VECTOR_DB_DIR if os.getenv("CHEMQA_INDEX_DIR") else "data/processed",
    )
    OUTPUT_DIR = path_setting("CHEMQA_OUTPUT_DIR", "output")

    # 文本处理参数
    LEGACY_CHUNK_WORDS = 500
    LEGACY_CHUNK_OVERLAP_WORDS = 50
    CHUNK_OVERLAP_TOKENS = 16

    # 向量存储配置
    EMBEDDING_MODEL = os.getenv(
        "CHEMQA_EMBEDDING_MODEL",
        "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
    )
    EMBEDDING_MODEL_REVISION = (
        os.getenv(
            "CHEMQA_EMBEDDING_REVISION",
            "e8f8c211226b894fcb81acc59f3b34ba3efd5f42"
            if EMBEDDING_MODEL
            == "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
            else "",
        )
        or None
    )
    # Optional pinned candidate profile; default remains the frozen MiniLM index.
    EMBEDDING_PROFILE = os.getenv("CHEMQA_EMBEDDING_PROFILE") or None
    RETRIEVAL_TOP_K = 10

    # Chat Completions configuration; DEEPSEEK_* names retain compatibility.
    DEEPSEEK_API_CONFIG: ClassVar[dict[str, str | float | int]] = {
        "api_key": os.getenv("DEEPSEEK_API_KEY", "").strip(),
        "base_url": os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com").rstrip(
            "/"
        ),
        "model": os.getenv("DEEPSEEK_MODEL", "deepseek-flash"),
        "temperature": float(os.getenv("DEEPSEEK_TEMPERATURE", "0.3")),
        "thinking": os.getenv("DEEPSEEK_THINKING", "disabled").strip(),
        "connect_timeout": float(os.getenv("DEEPSEEK_CONNECT_TIMEOUT", "10")),
        "read_timeout": float(os.getenv("DEEPSEEK_READ_TIMEOUT", "120")),
        "max_attempts": int(os.getenv("DEEPSEEK_MAX_ATTEMPTS", "3")),
    }

    # PDF解析设置
    PDF_PARSING_ENGINE = "pymupdf"

    # 系统配置保持不变
    DOMAIN = "organic electrocatalysis"
    MAX_TOKENS = int(os.getenv("DEEPSEEK_MAX_TOKENS", "4096"))

    MODEL_DIR = path_setting("CHEMQA_MODEL_DIR", "models")


settings = Settings()


def configure_paths(*, index_dir=None, output_dir=None):
    """CLI overrides take priority; all relative paths remain project-relative."""
    if index_dir is not None:
        settings.VECTOR_DB_DIR = str(resolve_path(index_dir))
        settings.PROCESSED_DIR = settings.VECTOR_DB_DIR
    if output_dir is not None:
        settings.OUTPUT_DIR = str(resolve_path(output_dir))
