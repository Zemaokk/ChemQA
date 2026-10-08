"""Publish isolated artifact directories only after all required files are written."""

import hashlib
import json
import os
import shutil
import tempfile
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from config.settings import BASE_DIR, resolve_path, settings


def sha256_file(path: Path) -> str:
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def config_record() -> dict:
    profile = (
        json.loads(resolve_path(settings.EMBEDDING_PROFILE).read_text(encoding="utf-8"))
        if settings.EMBEDDING_PROFILE
        else {}
    )
    return {
        "raw_papers_dir": settings.RAW_PAPERS_DIR,
        "index_dir": settings.VECTOR_DB_DIR,
        "processed_dir": settings.PROCESSED_DIR,
        "output_dir": settings.OUTPUT_DIR,
        "model_dir": settings.MODEL_DIR,
        "embedding_model": profile.get("model", settings.EMBEDDING_MODEL),
        "embedding_revision": profile.get(
            "revision", settings.EMBEDDING_MODEL_REVISION
        ),
        "embedding_profile": settings.EMBEDDING_PROFILE,
        "retrieval_top_k": settings.RETRIEVAL_TOP_K,
        "chunk_overlap_tokens": settings.CHUNK_OVERLAP_TOKENS,
        "api_model": settings.DEEPSEEK_API_CONFIG["model"],
        "api_temperature": settings.DEEPSEEK_API_CONFIG["temperature"],
        "max_output_tokens": settings.MAX_TOKENS,
        "api_thinking": settings.DEEPSEEK_API_CONFIG["thinking"],
        "api_connect_timeout": settings.DEEPSEEK_API_CONFIG["connect_timeout"],
        "api_read_timeout": settings.DEEPSEEK_API_CONFIG["read_timeout"],
        "api_max_attempts": settings.DEEPSEEK_API_CONFIG["max_attempts"],
        "uv_lock_sha256": sha256_file(Path(BASE_DIR) / "uv.lock"),
    }


@contextmanager
def atomic_text_writer(path: Path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            delete=False,
        ) as handle:
            temporary = Path(handle.name)
            yield handle
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def write_json(path: Path, value: dict):
    with atomic_text_writer(path) as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def write_text(path: Path, value: str):
    with atomic_text_writer(path) as handle:
        handle.write(value)


class ArtifactRun:
    def __init__(self, kind: str, *, destination=None):
        if destination is None:
            identifier = datetime.now(UTC).strftime("%Y%m%dT%H%M%S") + "-" + uuid4().hex
            self.target = resolve_path(settings.OUTPUT_DIR) / kind / identifier
        else:
            self.target = resolve_path(destination)
        self.target.parent.mkdir(parents=True, exist_ok=True)
        if self.target.exists():
            raise FileExistsError(
                f"Refusing to overwrite artifact directory: {self.target}"
            )
        self.path = Path(tempfile.mkdtemp(prefix=".staging-", dir=self.target.parent))
        self.kind = kind

    def __enter__(self):
        return self

    def publish(self, status: str, metadata: dict | None = None) -> Path:
        if self.target.exists():
            raise FileExistsError(f"Artifact directory already exists: {self.target}")
        write_json(
            self.path / "run.json",
            {
                "schema": "chemqa-artifact-run-v1",
                "kind": self.kind,
                "status": status,
                "created_utc": datetime.now(UTC).isoformat(),
                "config": config_record(),
                **(metadata or {}),
            },
        )
        # Both directories are siblings: publication stays on one filesystem.
        self.path.rename(self.target)
        return self.target

    def __exit__(self, *exc):
        if self.path.exists():
            shutil.rmtree(self.path)


def create_session(kind: str, metadata: dict | None = None) -> Path:
    with ArtifactRun(kind) as run:
        return run.publish("running", metadata)


def finish_session(path: Path, counts: dict):
    manifest = path / "run.json"
    if manifest.is_file():
        record = json.loads(manifest.read_text(encoding="utf-8"))
        record.update(status="complete", counts=counts)
        write_json(manifest, record)
