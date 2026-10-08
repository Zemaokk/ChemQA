"""Prepare a fresh source snapshot without Git history, credentials or datasets."""

import argparse
import json
import shutil
from pathlib import Path

from config.settings import BASE_DIR
from scripts.audit_secrets import audit, git, scan_lines
from src.utils.artifacts import ArtifactRun, sha256_file, write_json

SOURCE_TREES = {"config", "src", "scripts", "tests", "docs", "evaluation"}
TOP_LEVEL = {
    "main.py",
    "README.md",
    "LICENSE",
    "LICENSE.md",
    "pyproject.toml",
    "uv.lock",
    "requirements.txt",
    ".python-version",
    ".gitignore",
    ".env.example",
}


def include_source(path):
    path = Path(path)
    if any(part in {".git", "__pycache__", ".venv", ".env"} for part in path.parts):
        return False
    if path.name.startswith(".env"):
        return path.as_posix() == ".env.example"
    if len(path.parts) == 1:
        return path.name in TOP_LEVEL
    if path.parts[0] in SOURCE_TREES:
        return path.suffix.lower() in {
            ".py",
            ".pyi",
            ".md",
            ".json",
            ".toml",
            ".yaml",
            ".yml",
            ".txt",
        }
    return (
        path.parts[0] in {"qa_testing", "heatmap_visualization"}
        and len(path.parts) == 2
        and (path.suffix == ".py" or path.name.startswith("README"))
    )


def prepare(root, *, destination=None):
    root = Path(root).resolve()
    current = audit(root)
    if not current["current_clean"]:
        raise ValueError(
            "Current source contains key patterns; release was not prepared"
        )
    candidates = git(
        root, "ls-files", "--cached", "--others", "--exclude-standard", "-z"
    ).split(b"\0")
    files = {}
    with ArtifactRun("source_releases", destination=destination) as run:
        for raw in sorted(set(filter(None, candidates))):
            relative = Path(raw.decode())
            source = root / relative
            if (
                not include_source(relative)
                or not source.is_file()
                or source.is_symlink()
            ):
                continue
            target = run.path / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
            # Validate the actual copied bytes, including text extensions outside
            # the general audit allowlist. Nothing is published on a match.
            with target.open("rb") as handle:
                findings, _ = scan_lines(handle)
            if findings:
                raise ValueError(
                    "Copied source contains key patterns; release was not published"
                )
            files[relative.as_posix()] = sha256_file(target)
        write_json(
            run.path / "SOURCE_RELEASE.json",
            {
                "schema": "chemqa-source-release-v1",
                "files_sha256": files,
                "contains_git_history": False,
                "contains_local_env": False,
                "contains_literature_or_vectors": False,
                "limitations": "Source snapshot only. Supply local PDFs, compatible index, model cache and API configuration separately. This does not modify existing repository history or publish anything.",
            },
        )
        target = run.publish(
            "prepared", {"file_count": len(files), "key_pattern_matches": 0}
        )
    return target


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(BASE_DIR))
    parser.add_argument(
        "--destination", type=Path, help="New directory; existing targets are refused"
    )
    args = parser.parse_args()
    print(
        json.dumps(
            {"source_release": str(prepare(args.root, destination=args.destination))}
        )
    )


if __name__ == "__main__":
    main()
