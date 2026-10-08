"""Report API-key patterns in Git-managed text without printing secret values.

The default scans tracked and unignored untracked working-tree text. --staged
scans Git's exact index instead. --history adds reachable text blobs <= 2 MiB.
An exit code of 1 means matches exist, including historical matches when enabled.
This is a bounded pattern audit, not a comprehensive secret scanner.
"""

import argparse
import hashlib
import json
import re
import subprocess
from datetime import UTC, datetime
from pathlib import Path

KEY_PATTERN = re.compile(rb"(?<![A-Za-z0-9])sk-[A-Za-z0-9_-]{16,}")
TEXT_SUFFIXES = {
    ".py",
    ".pyi",
    ".md",
    ".txt",
    ".json",
    ".toml",
    ".yml",
    ".yaml",
    ".ini",
    ".cfg",
    ".env",
    ".example",
    ".sh",
    ".ipynb",
    ".pem",
}
HISTORY_LIMIT = 2 * 1024 * 1024


def git(root, *args, input_bytes=None):
    return subprocess.check_output(["git", "-C", str(root), *args], input=input_bytes)


def is_text_path(path):
    path = Path(path)
    return (
        path.suffix.lower() in TEXT_SUFFIXES
        or path.name.startswith(".env")
        or path.name in {"Dockerfile", "Makefile", ".gitignore", ".python-version"}
    )


def scan_lines(lines):
    """Keep only line numbers and internal digests; never return matching values."""
    findings = []
    digests = set()
    for number, line in enumerate(lines, 1):
        matches = KEY_PATTERN.findall(line)
        if matches:
            findings.append({"line": number, "occurrences": len(matches)})
            digests.update(hashlib.sha256(value).digest() for value in matches)
    return findings, digests


def scan_blob(root, oid):
    with subprocess.Popen(
        ["git", "-C", str(root), "cat-file", "blob", oid],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
    ) as process:
        findings, digests = scan_lines(process.stdout)
        if process.wait():
            raise ValueError("Could not read a Git blob")
    return findings, digests


def audit(root, *, history=False, staged=False):
    root = Path(root).resolve()
    report = {
        "schema": "chemqa-secret-audit-v1",
        "created_utc": datetime.now(UTC).isoformat(),
        "pattern": "sk-prefixed tokens with at least 16 suffix characters",
        "current_source": "git_index"
        if staged
        else "working_tree_and_unignored_untracked",
        "current": {"text_files_scanned": 0, "findings": []},
        "history": {
            "requested": history,
            "text_blobs_scanned": 0,
            "findings": [],
            "oversized_text_blobs_skipped": [],
            "max_blob_bytes": HISTORY_LIMIT,
        },
        "limitations": [
            "Pattern audit only; other credential formats are not covered.",
            "Binary/unknown-extension files and ignored local files are excluded.",
            "History checks local --all refs, not remote-only refs, reflogs, unreachable objects, clones or caches.",
            "Historical text blobs above the declared size limit are listed but not scanned.",
            "Account-side revocation is not verified by this script.",
        ],
    }
    current_keys, history_keys = set(), set()
    if staged:
        entries = git(root, "ls-files", "--stage", "-z").split(b"\0")
        for entry in filter(None, entries):
            metadata, path_bytes = entry.split(b"\t", 1)
            mode, oid, stage = metadata.decode().split()
            if stage != "0":
                raise ValueError(
                    "Resolve merge conflicts before scanning the Git index"
                )
            path = path_bytes.decode()
            if mode == "160000" or not is_text_path(path):
                continue
            findings, digests = scan_blob(root, oid)
            report["current"]["text_files_scanned"] += 1
            current_keys.update(digests)
            if findings:
                report["current"]["findings"].append({"path": path, "lines": findings})
    else:
        paths = git(
            root, "ls-files", "--cached", "--others", "--exclude-standard", "-z"
        ).split(b"\0")
        for path_bytes in sorted(set(filter(None, paths))):
            path = path_bytes.decode()
            file = root / path
            if not is_text_path(path) or not file.is_file() or file.is_symlink():
                continue
            with file.open("rb") as handle:
                findings, digests = scan_lines(handle)
            report["current"]["text_files_scanned"] += 1
            current_keys.update(digests)
            if findings:
                report["current"]["findings"].append({"path": path, "lines": findings})
    if history:
        objects = {}
        for entry in git(root, "rev-list", "--objects", "--all").decode().splitlines():
            oid, separator, path = entry.partition(" ")
            if separator and is_text_path(path):
                objects[oid] = path
        if objects:
            sizes = (
                git(
                    root,
                    "cat-file",
                    "--batch-check=%(objectname) %(objecttype) %(objectsize)",
                    input_bytes=("\n".join(objects) + "\n").encode(),
                )
                .decode()
                .splitlines()
            )
            for metadata in sizes:
                oid, kind, size = metadata.split()
                if kind != "blob":
                    continue
                path = objects[oid]
                if int(size) > HISTORY_LIMIT:
                    report["history"]["oversized_text_blobs_skipped"].append(
                        {"blob": oid, "path": path, "bytes": int(size)}
                    )
                    continue
                findings, digests = scan_blob(root, oid)
                report["history"]["text_blobs_scanned"] += 1
                history_keys.update(digests)
                if findings:
                    report["history"]["findings"].append(
                        {"blob": oid, "path": path, "lines": findings}
                    )
    report["current"]["distinct_pattern_count"] = len(current_keys)
    report["history"]["distinct_pattern_count"] = len(history_keys)
    report["current_clean"] = not current_keys
    report["history_clean"] = not history_keys if history else None
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root", type=Path, default=Path(__file__).resolve().parents[1]
    )
    parser.add_argument("--history", action="store_true")
    parser.add_argument("--staged", action="store_true")
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    report = audit(args.root, history=args.history, staged=args.staged)
    serialized = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(serialized, encoding="utf-8")
    print(serialized, end="")
    raise SystemExit(
        0 if report["current_clean"] and report["history_clean"] is not False else 1
    )


if __name__ == "__main__":
    main()
