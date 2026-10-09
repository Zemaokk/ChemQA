"""Check current documentation links, retired paths, and local archive integrity."""

import json
import re
import subprocess
from pathlib import Path
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]


def anchors(text):
    text = re.sub(r"```.*?```", "", text, flags=re.DOTALL)
    result = set(re.findall(r'\bid=["\']([^"\']+)["\']', text))
    seen = {}
    for heading in re.findall(r"^#{1,6}\s+(.+?)\s*#*\s*$", text, re.MULTILINE):
        slug = re.sub(r"[^\w\- ]", "", heading.lower()).replace(" ", "-")
        count = seen.get(slug, 0)
        seen[slug] = count + 1
        result.add(slug if count == 0 else f"{slug}-{count}")
    return result


def check(root=ROOT):
    root = Path(root).resolve()
    pages = (
        sorted((root / "docs").rglob("*.md"))
        + [root / name for name in ("README.md", "CONTRIBUTING.md", "CHANGELOG.md")]
        + [root / "data/README.md"]
    )
    errors = []
    link_count = 0
    for page in pages:
        text = page.read_text(encoding="utf-8")
        if text.count("```") % 2:
            errors.append(f"{page.relative_to(root)}: unclosed code fence")
        body = re.sub(r"```.*?```", "", text, flags=re.DOTALL)
        links = re.findall(r"\]\((<[^>]+>|[^\s)]+)\)", body)
        links += re.findall(r'(?:href|src)=["\']([^"\']+)["\']', body)
        for link in links:
            link_count += 1
            parsed = urlsplit(link.strip("<>"))
            if parsed.scheme or parsed.netloc:
                continue
            target = (
                (page.parent / unquote(parsed.path)).resolve() if parsed.path else page
            )
            label = f"{page.relative_to(root)}: {link}"
            if not target.exists():
                errors.append(f"Missing target: {label}")
            elif "legacy-docs" in target.parts:
                errors.append(f"Current guide depends on ignored archive: {label}")
            elif (
                parsed.fragment
                and target.suffix == ".md"
                and unquote(parsed.fragment) not in anchors(target.read_text())
            ):
                errors.append(f"Missing anchor: {label}")

    migration = json.loads(
        (root / "docs/reference/documentation-migration.json").read_text()
    )
    retired = {
        path for path in migration["prose_replacements"] if not (root / path).exists()
    }
    for pattern in ("scripts/*.py", "src/**/*.py", "config/*.py"):
        for source in root.glob(pattern):
            text = source.read_text()
            for path in retired:
                if path in text:
                    errors.append(
                        f"Retired document in {source.relative_to(root)}: {path}"
                    )
    for path in retired:
        if path in (root / ".env.example").read_text():
            errors.append(f"Retired document in .env.example: {path}")

    archive = root / migration["archive"]
    archived_count = 0
    if archive.exists():
        import hashlib

        manifest = json.loads((archive / "MANIFEST.json").read_text())
        for relative, digest in manifest["files_sha256"].items():
            target = archive / relative
            if (
                not target.is_file()
                or hashlib.sha256(target.read_bytes()).hexdigest() != digest
            ):
                errors.append(f"Archive missing or changed: {relative}")
            archived_count += 1
        ignored = subprocess.run(
            ["git", "check-ignore", "--quiet", str(archive / "MANIFEST.json")],
            cwd=root,
            check=False,
        )
        if ignored.returncode:
            errors.append("Local documentation archive is not Git-ignored")

    from scripts.prepare_source_release import include_source

    for relative in (
        "legacy-docs/2026-10-09/README.md",
        "docs/legacy-docs/old.md",
    ):
        if include_source(relative):
            errors.append(f"Source snapshot includes archive: {relative}")
    for relative in (
        "README.md",
        "CHANGELOG.md",
        "CONTRIBUTING.md",
        "docs/README.md",
        "data/README.md",
    ):
        if not include_source(relative):
            errors.append(f"Source snapshot omits current entry point: {relative}")
    return {
        "pages_checked": len(pages),
        "links_checked": link_count,
        "archived_files_verified": archived_count,
        "errors": errors,
    }


def main():
    result = check()
    print(json.dumps(result, indent=2))
    raise SystemExit(bool(result["errors"]))


if __name__ == "__main__":
    main()
