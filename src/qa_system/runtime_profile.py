"""Explicit frozen local runtimes; validation never loads models or sends requests."""

import json

from config.settings import configure_paths, resolve_path, settings
from src.utils.artifacts import sha256_file

MANIFEST = "config/r01_runtime.json"


def validate_runtime(name, *, manifest_path=MANIFEST):
    path = resolve_path(manifest_path)
    manifest = json.loads(path.read_text())
    if manifest["schema"] != "chemqa-runtime-freeze-v1":
        raise ValueError("Unsupported runtime freeze schema")
    profile = manifest["profiles"][name]
    # Hashes bind local artifacts and implementation, not scientific correctness.
    for filename, expected in {
        **manifest["shared_files_sha256"],
        **profile["files_sha256"],
    }.items():
        target = resolve_path(filename)
        if not target.is_file() or sha256_file(target) != expected:
            raise ValueError(f"Frozen runtime file missing or changed: {filename}")
    return (
        manifest,
        profile,
        {
            "profile": name,
            "manifest_sha256": sha256_file(path),
            "adoption_status": manifest["adoption_status"],
        },
    )


def configure_runtime(name, *, manifest_path=MANIFEST):
    """Validate before mutating settings; retain only the externally supplied key."""
    manifest, profile, provenance = validate_runtime(name, manifest_path=manifest_path)
    generation = manifest["generation"]
    shadow = resolve_path("models") / profile["embedding_model"]
    if shadow.exists():
        raise ValueError(
            "Frozen runtime requires pinned Hub revision, not a local shadow"
        )
    configure_paths(index_dir=profile["index_directory"])
    settings.PROCESSED_DIR = str(resolve_path(profile["processed_directory"]))
    settings.EMBEDDING_MODEL = profile["embedding_model"]
    settings.EMBEDDING_MODEL_REVISION = profile["embedding_revision"]
    settings.EMBEDDING_PROFILE = profile["embedding_profile"]
    settings.MODEL_DIR = str(resolve_path("models"))
    settings.RETRIEVAL_TOP_K = 10
    settings.DOMAIN = generation["domain"]
    settings.MAX_TOKENS = generation["body"]["max_tokens"]
    settings.DEEPSEEK_API_CONFIG = {
        **settings.DEEPSEEK_API_CONFIG,
        "base_url": generation["base_url"],
        "model": generation["body"]["model"],
        "temperature": generation["body"]["temperature"],
        "thinking": generation["body"]["thinking"]["type"],
        "max_attempts": generation["max_attempts"],
        "connect_timeout": generation["connect_timeout"],
        "read_timeout": generation["read_timeout"],
    }
    return {
        "reranker_profile": profile["reranker_profile"],
        "context_policy": profile["context_policy"],
    }, provenance
